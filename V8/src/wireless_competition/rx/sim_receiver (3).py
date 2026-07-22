"""简化仿真接收端。

用于纯软件仿真测试，跳过复杂的帧检测，直接从已知位置提取符号。
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
    decode_header,
)
from ..file_protocol.integrity import check_crc32
from ..tx.framing import make_preamble, make_sync_word
from ..tx.modulation import bits_to_bytes, bytes_to_bits
from ..tx.fec import convolutional_decode_hard
from ..tx.pulse_shaping import matched_filter, downsample
from .carrier import CostasLoop
from .cfo import estimate_cfo_from_preamble, correct_cfo
from .decoder import Decoder
from .demodulation import (
    compute_evm,
    demodulate_hard,
    demodulate_soft,
    estimate_noise_std,
)


class SimulationReceiver:
    """简化仿真接收端。

    在仿真中，帧边界已知（由 TX 提供），跳过帧检测步骤。
    直接进行匹配滤波、定时、CFO、解调、译码。
    """

    def __init__(
        self,
        profile: RxProfile = RxProfile(),
        seed: Optional[int] = None,
    ):
        self.profile = profile
        self._rng = create_rng(seed)
        self._sps = profile.samples_per_symbol
        self._rolloff = profile.rrc_rolloff
        self._span = profile.rrc_span

        self._preamble = make_preamble(self._sps, 64, "pn")
        self._sync_word = make_sync_word()
        self._preamble_len = len(self._preamble)
        self._sync_len = len(self._sync_word)

        self._decoder = Decoder(fec_type=profile.fec_type)
        self._costas = CostasLoop(
            loop_bandwidth=0.01,
            is_qpsk=(profile.modulation == ModulationType.QPSK),
        )

    def process_frame(
        self,
        iq_signal: np.ndarray,
        sample_rate_hz: float = 2.0e6,
        guard_symbols: int = 16,
    ) -> DecodeResult:
        """处理单帧 IQ，帧起始对齐到信号开头。

        假设 iq_signal 从帧的第一个样本开始（guard 已被剥离或包含在信号中）。
        帧结构：[guard_sym] [preamble_sym] [sync_sym] [header_sym] [pilot_sym] [payload_sym] [guard_sym]

        Args:
            iq_signal: 单帧 IQ 波形（过采样）。
            sample_rate_hz: 采样率。

        Returns:
            DecodeResult。
        """
        t0 = time.perf_counter()
        sps = self._sps
        guard_sym = int(guard_symbols)

        if guard_sym < 0:
            raise ValueError("guard_symbols must be non-negative")

        result = DecodeResult(
            frame_detected=True,
            profile_used=self.profile.profile_id,
        )

        if len(iq_signal) < (guard_sym + self._preamble_len) * sps:
            result.failure_reason = FailureReason.NO_FRAME_DETECTED
            result.processing_time_s = time.perf_counter() - t0
            return result

        # 1. 匹配滤波
        mf_iq = matched_filter(iq_signal, sps, self._rolloff, self._span)

        if len(mf_iq) < sps * 10:
            result.failure_reason = FailureReason.NO_FRAME_DETECTED
            result.processing_time_s = time.perf_counter() - t0
            return result

        # 2. 先定位前导（guard 移到 IQ 级后，MF 输出中前导在 guard_symbols±span 范围）
        # 同时用最佳偏移做 CFO 估计
        from ..tx.pulse_shaping import downsample as ds

        best_offset = 0
        best_peak = -1.0
        best_pos = -1
        for off in range(sps):
            sym = mf_iq[off::sps]
            if len(sym) < guard_symbols + self._preamble_len:
                continue
            # 搜索范围放宽到 guard ± span 符号（覆盖 RRC 群延迟）
            search_start = max(0, guard_symbols - self._span)
            search_end = min(len(sym) - self._preamble_len, guard_symbols + self._span * 2)
            for pos in range(search_start, search_end):
                seg = sym[pos:pos + self._preamble_len]
                c = np.abs(np.dot(seg, self._preamble.conj()))
                if c > best_peak:
                    best_peak = c
                    best_offset = off
                    best_pos = pos

        symbols_full = mf_iq[best_offset::sps]
        preamble_sym_offset = best_pos

        if preamble_sym_offset < 0 or len(symbols_full) < preamble_sym_offset + self._preamble_len + self._sync_len + 20:
            result.failure_reason = FailureReason.NO_FRAME_DETECTED
            result.processing_time_s = time.perf_counter() - t0
            return result

        # 验证 sync word（高阈值：前导完美匹配后同步字也应完美匹配）
        sync_check_start = preamble_sym_offset + self._preamble_len
        if sync_check_start + self._sync_len <= len(symbols_full):
            sync_seg = symbols_full[sync_check_start:sync_check_start + self._sync_len]
            sync_corr = np.abs(np.dot(sync_seg, self._sync_word.conj()))
            if sync_corr < 0.6 * self._sync_len:  # 同步字必须显著匹配
                result.failure_reason = FailureReason.NO_FRAME_DETECTED
                result.processing_time_s = time.perf_counter() - t0
                return result

        result.sync_state = SyncState.TIMING_LOCKED

        # 3. CFO 估计与校正（用已定位的前导区域）
        pre_mf_start = preamble_sym_offset * sps
        pre_mf_end = (preamble_sym_offset + self._preamble_len) * sps
        preamble_mf = mf_iq[pre_mf_start:pre_mf_end]
        cfo_hz = estimate_cfo_from_preamble(
            preamble_mf, self._preamble, sps, sample_rate_hz
        )
        result.cfo_estimate_hz = cfo_hz
        if abs(cfo_hz) > 0.1:
            mf_iq = correct_cfo(mf_iq, cfo_hz, sample_rate_hz)
            # CFO 校正后重新提取符号
            symbols_full = mf_iq[best_offset::sps]
        result.sync_state = SyncState.CFO_CORRECTED

        # 5. 同步字验证
        sync_start = preamble_sym_offset + self._preamble_len
        if sync_start + self._sync_len <= len(symbols_full):
            sync_region = symbols_full[sync_start:sync_start + self._sync_len]
            sync_corr = np.abs(np.correlate(sync_region, self._sync_word.conj()))
            if len(sync_corr) > 0 and np.max(sync_corr) < 0.3 * self._sync_len:
                pass  # 继续尝试

        # 6. 载波相位跟踪
        self._costas.reset()
        costas_start = sync_start + self._sync_len

        # 7. 包头解码
        header_bits_count = HEADER_LENGTH_BYTES * 8 * 2  # 卷积码 rate 1/2
        header_sym_end = costas_start + header_bits_count

        if header_sym_end > len(symbols_full):
            result.failure_reason = FailureReason.HEADER_CRC_FAIL
            result.processing_time_s = time.perf_counter() - t0
            return result

        header_syms = symbols_full[costas_start:header_sym_end]
        header_corrected = self._costas.process_batch(header_syms)
        header_bits = demodulate_hard(header_corrected, ModulationType.BPSK)
        # 包头始终使用卷积码编码，不受 payload FEC 参数影响
        header_decoded = convolutional_decode_hard(header_bits)[:HEADER_LENGTH_BYTES * 8]
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

        result.header_crc_pass = True
        result.sync_state = SyncState.HEADER_DECODED

        # 8. 导频跳过
        pilot_bits = 128
        payload_start = header_sym_end + pilot_bits

        remaining = max(0, len(symbols_full) - payload_start)
        if remaining < 10:
            result.failure_reason = FailureReason.PAYLOAD_CRC_FAIL
            result.processing_time_s = time.perf_counter() - t0
            return result

        crc_overhead = 4  # CRC-32 字节
        bits_per_symbol = 2 if self.profile.modulation == ModulationType.QPSK else 1
        raw_payload_bits = (meta.payload_length + crc_overhead) * 8
        available_coded_bits = remaining * bits_per_symbol
        if self.profile.fec_type == FECType.NONE:
            payload_bit_count = min(available_coded_bits, raw_payload_bits)
            coded_bits_needed = payload_bit_count
        else:
            # 当前卷积码固定 rate 1/2：两个 coded bits 对应一个原始 bit。
            payload_bit_count = min(available_coded_bits // 2, raw_payload_bits)
            coded_bits_needed = payload_bit_count * 2

        payload_symbol_count = (coded_bits_needed + bits_per_symbol - 1) // bits_per_symbol
        payload_syms = symbols_full[payload_start:payload_start + payload_symbol_count]
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
        crc_len = meta.payload_length + crc_overhead
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
