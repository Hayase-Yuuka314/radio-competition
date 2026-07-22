"""DSSS 集成流水线。

将对抗模块集成到主 TX/RX 流水线中。
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from ..adversarial.dsss import SpreadingCodeManager, spread, despread
from ..common.types import (
    ChannelConfig, DecodeResult, FECType, FrameMetadata,
    ModulationType, RxProfile,
)
from ..file_protocol.assembler import FileAssembler
from ..tx.pipeline import TXPipeline
from ..rx.sim_receiver import SimulationReceiver
from ..channel.pipeline import ChannelPipeline


class DSSSTXPipeline:
    """DSSS 增强发射流水线。

    在传统 TXPipeline 的调制和脉冲成形之间插入 DSSS 扩频。
    流程：文件分块 → 组帧(BPSK) → DSSS扩频 → IQ波形
    """

    def __init__(
        self,
        team_id: int = 0,
        code_length: int = 255,
        block_size: int = 256,
        seed: Optional[int] = None,
    ):
        self._code_mgr = SpreadingCodeManager(our_team_id=team_id, code_length=code_length)
        self._code = self._code_mgr.our_code
        self._code_length = code_length
        self._team_id = team_id

        # 内部传统 TX（BPSK 调制后不脉冲成形，我们用 DSSS 码片替代）
        self._tx = TXPipeline(
            modulation=ModulationType.BPSK,
            fec_type=FECType.NONE,
            block_size=block_size,
            seed=seed,
        )

    @property
    def code_length(self) -> int:
        return self._code_length

    @property
    def processing_gain_db(self) -> float:
        return 10.0 * np.log10(self._code_length)

    def process_file(self, data: bytes) -> list[np.ndarray]:
        """处理完整文件，返回 DSSS 扩频后的 IQ 帧列表。

        每帧 IQ 波形 = BPSK 符号序列经 DSSS 扩频后的码片序列。
        """
        # 传统 TX 生成帧（但不做脉冲成形，我们手动替换）
        # 复用 TXPipeline 的分块和组帧逻辑
        frames = self._tx.process_file(data)

        dsss_frames = []
        for frame_iq in frames:
            # frame_iq 是脉冲成形后的过采样波形
            # 我们需要绕过脉冲成形，直接从符号级做 DSSS
            # 这里用简化方式：把 frame_iq 当作 BPSK 符号的近似
            # 更准确的做法是重构 build_frame
            pass

        # 更简洁的方法：直接用 build_frame 拿到符号，然后 spread
        return self._process_file_direct(data)

    def _process_file_direct(self, data: bytes) -> list[np.ndarray]:
        """直接方式：分块 → 组帧(符号级) → DSSS扩频 → IQ码片。"""
        from ..file_protocol.chunker import chunk_file_with_metadata
        from ..tx.framing import build_frame
        from ..tx.pulse_shaping import pulse_shape

        chunks = chunk_file_with_metadata(data, self._tx.file_id, self._tx.block_size)
        frames = []

        for fid, seq, total, payload in chunks:
            meta = FrameMetadata(
                protocol_version=1,
                file_id=fid,
                session_id=self._tx.session_id,
                block_sequence=seq,
                total_blocks=total,
                payload_length=len(payload),
                profile_id=self._tx.profile_id,
            )

            # 1. 生成 BPSK 符号级帧
            bpsk_frame = build_frame(
                payload=payload,
                metadata=meta,
                modulation=ModulationType.BPSK,
                fec_type=FECType.NONE,
                samples_per_symbol=1,        # 符号级
                rolloff=0.35,
                span=6,
                preamble_length_symbols=64,
                guard_length_symbols=16,
            )

            # bpsk_frame 包含脉冲成形和 guard，我们需要提取纯符号
            # 简化：直接用 build_frame 的输出做 DSSS
            # DSSS 在 IQ 采样级操作：每个 ±1 符号替换为 N 个码片

            # 2. 提取 BPSK 符号（近似：脉冲成形后的峰值采样）
            from ..tx.pulse_shaping import matched_filter
            sps = self._tx.samples_per_symbol
            mf = matched_filter(bpsk_frame, sps)

            # 在匹配滤波输出中取符号（每 sps 个样本取一个）
            # 找到最佳偏移
            best_peak = -1
            best_off = 0
            for off in range(sps):
                sym = mf[off::sps]
                if len(sym) > 10:
                    power = np.mean(np.abs(sym[:min(200, len(sym))]) ** 2)
                    if power > best_peak:
                        best_peak = power
                        best_off = off

            symbols = mf[best_off::sps]

            # 3. DSSS 扩频：每个符号展开为 code_length 个码片
            sym_real = np.sign(np.real(symbols))  # 硬判为 ±1
            chips = spread(sym_real, self._code)

            # 4. 可选脉冲成形（简化：直接输出码片）
            frames.append(chips)

        return frames


class DSSSRXPipeline:
    """DSSS 增强接收流水线。

    在匹配滤波之后、解调之前插入 DSSS 解扩。
    """

    def __init__(
        self,
        team_id: int = 0,
        code_length: int = 255,
        block_size: int = 256,
        seed: Optional[int] = None,
    ):
        self._code_mgr = SpreadingCodeManager(our_team_id=team_id, code_length=code_length)
        self._code = self._code_mgr.our_code
        self._code_length = code_length
        self._team_id = team_id
        self._block_size = block_size

        # 内部传统 RX（处理解扩后的符号）
        self._rx = SimulationReceiver(
            profile=RxProfile(modulation=ModulationType.BPSK, fec_type=FECType.NONE),
            seed=seed,
        )

    def process_frame(
        self,
        chips: np.ndarray,
        sample_rate_hz: float = 2.0e6,
    ) -> DecodeResult:
        """处理一帧 DSSS 码片。

        Args:
            chips: DSSS 码片序列（±1，从发射端直接发出）。
            sample_rate_hz: 采样率。

        Returns:
            DecodeResult。
        """
        # 1. DSSS 解扩：码片 → 符号
        # 码片速率是符号速率的 code_length 倍
        # 将码片按 code_length 分组，每组做内积恢复一个符号
        n_symbols = len(chips) // self._code_length
        if n_symbols == 0:
            from ..common.types import DecodeResult, FailureReason
            return DecodeResult(
                frame_detected=False,
                failure_reason=FailureReason.NO_FRAME_DETECTED,
            )

        chips_2d = chips[:n_symbols * self._code_length].reshape(n_symbols, self._code_length)
        symbols = np.dot(chips_2d, self._code)  # 软值（未经硬判）

        # 2. 重建"等效 BPSK 帧"给传统 RX
        # SimulationReceiver 期望脉冲成形后的 IQ 波形
        # 我们把解扩后的软值当作 BPSK 符号，做简单的上采样
        from ..tx.pulse_shaping import pulse_shape
        from ..tx.modulation import bpsk_modulate

        # 将软值硬判为 BPSK 符号
        bpsk_syms = bpsk_modulate((symbols <= 0).astype(np.uint8))
        # 脉冲成形（让传统 RX 的 MF 能工作）
        sps = 8
        frame_iq = pulse_shape(bpsk_syms, sps, 0.35, 6)

        # 3. 传统 RX 处理
        return self._rx.process_frame(frame_iq, sample_rate_hz, guard_symbols=16)


def run_dsss_end_to_end(
    data: bytes,
    team_id: int = 0,
    code_length: int = 255,
    snr_db: float = 10.0,
    block_size: int = 256,
    seed: int = 42,
) -> dict:
    """运行一次完整的 DSSS 端到端仿真。

    Args:
        data: 原始文件数据。
        team_id: 队伍编号。
        code_length: DSSS 码长。
        snr_db: 信噪比。
        block_size: 块大小。
        seed: 随机种子。

    Returns:
        指标字典。
    """
    rng = np.random.default_rng(seed)

    # TX
    tx = DSSSTXPipeline(team_id=team_id, code_length=code_length,
                        block_size=block_size, seed=seed)
    dsss_frames = tx._process_file_direct(data)

    # 信道
    channel = ChannelPipeline(ChannelConfig(snr_db=snr_db))

    # RX
    rx = DSSSRXPipeline(team_id=team_id, code_length=code_length,
                        block_size=block_size, seed=seed)
    assembler = FileAssembler()

    correct_bytes = 0
    total_frames = len(dsss_frames)
    failed_frames = 0

    for chips in dsss_frames:
        # 信道加噪
        ch_out = channel.apply(chips.astype(np.complex128), 2.0e6, rng)
        noisy_chips = np.real(ch_out.iq)  # DSSS 用实值

        # RX 解扩+解帧
        result = rx.process_frame(noisy_chips, 2.0e6)

        if result.payload_crc_pass and result.metadata is not None:
            seq = result.metadata.block_sequence
            start = seq * block_size
            end = min(start + len(result.payload_bytes), len(data))
            expected = data[start:end]
            correct_bytes += sum(
                1 for a, b in zip(expected, result.payload_bytes[:len(expected)])
                if a == b
            )
            assembler.accept_raw(
                file_id=result.metadata.file_id,
                block_seq=seq,
                total_blocks=result.metadata.total_blocks,
                payload=result.payload_bytes,
            )
        else:
            failed_frames += 1

    return {
        "total_frames": total_frames,
        "failed_frames": failed_frames,
        "correct_bytes": correct_bytes,
        "total_bytes": len(data),
        "complete": assembler.is_complete(0),
        "code_length": code_length,
        "processing_gain_db": tx.processing_gain_db,
        "snr_db": snr_db,
    }
