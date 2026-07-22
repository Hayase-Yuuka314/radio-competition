"""接收端流水线。

整合帧检测、同步、解调、译码和 CRC 校验全流程。
"""

from __future__ import annotations

import time
from typing import Optional

import numpy as np

from ..common.seeds import create_rng
from ..common.types import (
    DecodeResult,
    FailureReason,
    FECType,
    FrameMetadata,
    ModulationType,
    ProfileID,
    RxProfile,
    SyncState,
)
from ..file_protocol.frame_header import (
    HEADER_LENGTH_BYTES,
    HEADER_PAYLOAD_BYTES,
    decode_header,
)
from ..file_protocol.integrity import check_crc32
from ..tx.framing import make_preamble, make_sync_word
from ..tx.modulation import bytes_to_bits, bits_to_bytes
from .carrier import CostasLoop
from .cfo import correct_cfo, estimate_cfo_from_preamble
from .decoder import Decoder
from .demodulation import (
    compute_evm,
    demodulate_hard,
    demodulate_soft,
    estimate_noise_std,
)
from .detector import FrameDetector
from .timing import symbol_timing_by_correlation


class Receiver:
    """接收端流水线。

    处理 IQ 流，输出 DecodeResult 序列。
    """

    def __init__(
        self,
        profile: RxProfile = RxProfile(),
        seed: Optional[int] = None,
    ):
        self.profile = profile
        self._rng = create_rng(seed)

        # 子模块
        self._preamble_raw = make_preamble(
            profile.samples_per_symbol,
            64,  # 固定前导长度
        )
        self._sync_word = make_sync_word()

        self._detector = FrameDetector(
            preamble=self._preamble_raw,
            sync_word=self._sync_word,
            detection_threshold=profile.frame_detection_threshold,
            samples_per_symbol=profile.samples_per_symbol,
        )

        self._decoder = Decoder(
            fec_type=profile.fec_type,
            interleave_block_size=0,  # 从帧头获取
        )

        self._costas = CostasLoop(
            loop_bandwidth=0.01,
            is_qpsk=(profile.modulation == ModulationType.QPSK),
        )

    def process(
        self,
        iq_signal: np.ndarray,
        sample_rate_hz: float = 2.0e6,
    ) -> list[DecodeResult]:
        """处理一段 IQ 信号。

        Args:
            iq_signal: 接收 IQ 波形（过采样，已脉冲成形）。
            sample_rate_hz: 采样率。

        Returns:
            解码结果列表。
        """
        t_start = time.perf_counter()
        sps = self.profile.samples_per_symbol
        results: list[DecodeResult] = []

        # 帧检测（使用脉冲成形后的前导直接匹配原始信号）
        peaks = self._detector.detect(iq_signal)

        if not peaks:
            return [DecodeResult(
                frame_detected=False,
                failure_reason=FailureReason.NO_FRAME_DETECTED,
                sync_state=SyncState.IDLE,
                profile_used=self.profile.profile_id,
                processing_time_s=time.perf_counter() - t_start,
            )]

        for frame_start in peaks:
            result = self._process_single_frame(
                iq_signal, frame_start, sample_rate_hz
            )
            results.append(result)

        return results

    def _process_single_frame(
        self,
        iq_signal: np.ndarray,
        frame_start: int,
        sample_rate_hz: float,
    ) -> DecodeResult:
        """处理单个检测到的帧。

        iq_signal 是原始（脉冲成形后）的过采样 IQ，frame_start 近似为前导开始位置。
        """
        t0 = time.perf_counter()
        sps = self.profile.samples_per_symbol
        rolloff = self.profile.rrc_rolloff
        span = self.profile.rrc_span
        preamble_len = len(self._preamble_raw)
        sync_len = len(self._sync_word)
        shaped_preamble_len = len(self._detector.preamble_shaped)

        result = DecodeResult(
            frame_detected=True,
            profile_used=self.profile.profile_id,
        )

        # 提取帧区域（含 RRC 滤波器延迟余量）
        # frame_start 是检测到的近似前导开始位置
        # 我们需要足够的数据覆盖整帧
        margin = span * sps  # RRC 延迟
        region_start = max(0, frame_start - margin)
        region_end = min(len(iq_signal), frame_start + shaped_preamble_len + 200 * sps)
        frame_region = iq_signal[region_start:region_end]

        if len(frame_region) < preamble_len * sps:
            result.failure_reason = FailureReason.NO_FRAME_DETECTED
            result.processing_time_s = time.perf_counter() - t0
            return result

        # 0. 匹配滤波
        from ..tx.pulse_shaping import matched_filter as mf_func
        mf_iq = mf_func(frame_region, sps, rolloff, span)

        if len(mf_iq) < preamble_len * sps:
            result.failure_reason = FailureReason.NO_FRAME_DETECTED
            result.processing_time_s = time.perf_counter() - t0
            return result

        # 1. 符号定时（从 MF 输出中找到最佳下采样偏移）
        symbols, timing_offset = symbol_timing_by_correlation(
            mf_iq, self._preamble_raw, sps
        )
        if len(symbols) < preamble_len + sync_len + 20:
            result.failure_reason = FailureReason.NO_FRAME_DETECTED
            result.processing_time_s = time.perf_counter() - t0
            return result

        result.sync_state = SyncState.TIMING_LOCKED

        # 2. CFO 估计（从符号域）
        cfo_hz = estimate_cfo_from_preamble(
            mf_iq, self._preamble_raw, sps, sample_rate_hz
        )
        result.cfo_estimate_hz = cfo_hz

        # CFO 校正（在符号域做相位解旋？不，在采样域做更好，但这里简化）
        if abs(cfo_hz) > 0.1:
            # 在符号域校正
            t_sym = np.arange(len(symbols)) / (sample_rate_hz / sps)
            symbols = symbols * np.exp(-1j * 2 * np.pi * cfo_hz * t_sym).astype(np.complex128)

        result.sync_state = SyncState.CFO_CORRECTED

        # 3. 同步字验证
        sync_start = preamble_len
        if sync_start + sync_len <= len(symbols):
            sync_region = symbols[sync_start : sync_start + sync_len]
            sync_corr = np.abs(np.correlate(sync_region, self._sync_word.conj()))
            if len(sync_corr) > 0 and np.max(sync_corr) < 0.3 * sync_len:
                result.failure_reason = FailureReason.NO_FRAME_DETECTED
                result.processing_time_s = time.perf_counter() - t0
                return result

        # 4. 载波相位跟踪
        self._costas.reset()
        costas_start = sync_start + sync_len

        # 5. 解析包头（BPSK + 卷积码）
        header_encoded_bits_count = HEADER_LENGTH_BYTES * 8 * 2  # 卷积码 rate 1/2
        header_sym_end = costas_start + header_encoded_bits_count

        if header_sym_end > len(symbols):
            result.failure_reason = FailureReason.HEADER_CRC_FAIL
            result.processing_time_s = time.perf_counter() - t0
            return result

        header_syms = symbols[costas_start:header_sym_end]
        header_corrected = self._costas.process_batch(header_syms)

        header_bits = demodulate_hard(header_corrected, ModulationType.BPSK)
        header_decoded = self._decoder.decode_bits(
            header_bits, HEADER_LENGTH_BYTES * 8, is_soft=False
        )[0]
        header_bytes = bits_to_bytes(header_decoded)[:HEADER_LENGTH_BYTES]

        try:
            meta, header_crc_ok = decode_header(header_bytes)
        except Exception:
            result.failure_reason = FailureReason.HEADER_CRC_FAIL
            result.processing_time_s = time.perf_counter() - t0
            return result

        result.metadata = meta
        if not header_crc_ok:
            result.failure_reason = FailureReason.HEADER_CRC_FAIL
            result.processing_time_s = time.perf_counter() - t0
            return result

        result.sync_state = SyncState.HEADER_DECODED

        # 6. 导频
        pilot_bits = 128
        pilot_sym_len = pilot_bits  # BPSK
        payload_start = header_sym_end + pilot_sym_len

        # 7. 解调载荷（使用所有剩余符号）
        remaining = max(0, len(symbols) - payload_start)
        if remaining < 10:
            result.failure_reason = FailureReason.PAYLOAD_CRC_FAIL
            result.processing_time_s = time.perf_counter() - t0
            return result

        if self.profile.fec_type == FECType.NONE:
            payload_bit_count = min(remaining, (meta.payload_length + 4) * 8)
        else:
            payload_bit_count = min(remaining // 2, (meta.payload_length + 4) * 8)

        payload_syms = symbols[payload_start:payload_start + remaining]
        payload_corrected = self._costas.process_batch(payload_syms)
        result.sync_state = SyncState.PAYLOAD_DECODING

        noise_std = max(estimate_noise_std(
            payload_corrected[:min(500, len(payload_corrected))],
            self.profile.modulation
        ), 0.01)

        if self.profile.fec_type == FECType.NONE:
            payload_bits = demodulate_hard(payload_corrected, self.profile.modulation)
            payload_decoded = payload_bits[:payload_bit_count]
        else:
            llr = demodulate_soft(payload_corrected, self.profile.modulation, noise_std)
            payload_decoded = self._decoder.decode_bits(
                llr, payload_bit_count, is_soft=True, noise_std=noise_std
            )[0]

        payload_bytes = bits_to_bytes(payload_decoded[:payload_bit_count])

        # CRC
        crc_len = meta.payload_length + 4
        if len(payload_bytes) >= crc_len:
            payload_data, crc_ok = check_crc32(payload_bytes[:crc_len])
        else:
            crc_ok = False
            payload_data = b""

        if crc_ok:
            result.payload_crc_pass = True
            result.payload_bytes = payload_data[:meta.payload_length]
            result.sync_state = SyncState.CRC_PASS
        else:
            result.payload_crc_pass = False
            result.failure_reason = FailureReason.PAYLOAD_CRC_FAIL
            result.sync_state = SyncState.CRC_FAIL

        # 指标
        eval_syms = payload_corrected[:min(500, len(payload_corrected))]
        if len(eval_syms) > 0:
            result.evm_estimate = compute_evm(eval_syms, self.profile.modulation)
            result.snr_estimate_db = -20 * np.log10(result.evm_estimate + 1e-12) if result.evm_estimate > 0 else 30.0

        result.processing_time_s = time.perf_counter() - t0
        return result
