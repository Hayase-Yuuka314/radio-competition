"""发射端流水线。

将文件分块并按帧结构依次生成 IQ 波形。
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from ..common.seeds import create_rng
from ..common.types import FECType, FrameMetadata, ModulationType, ProfileID
from ..file_protocol.chunker import chunk_file_with_metadata
from .framing import build_frame


class TXPipeline:
    """发射端流水线。

    将输入文件分块，为每块构建物理层帧。
    """

    def __init__(
        self,
        modulation: ModulationType = ModulationType.BPSK,
        fec_type: FECType = FECType.NONE,
        samples_per_symbol: int = 8,
        rolloff: float = 0.35,
        span: int = 6,
        block_size: int = 256,
        interleave_block_size: int = 0,
        preamble_length_symbols: int = 64,
        guard_length_symbols: int = 16,
        file_id: int = 0,
        session_id: int = 0,
        profile_id: ProfileID = ProfileID.P1_ROBUST,
        seed: Optional[int] = None,
    ):
        self.modulation = modulation
        self.fec_type = fec_type
        self.samples_per_symbol = samples_per_symbol
        self.rolloff = rolloff
        self.span = span
        self.block_size = block_size
        self.interleave_block_size = interleave_block_size
        self.preamble_length_symbols = preamble_length_symbols
        self.guard_length_symbols = guard_length_symbols
        self.file_id = file_id
        self.session_id = session_id
        self.profile_id = profile_id
        self._rng = create_rng(seed)

    def process_file(self, data: bytes) -> list[np.ndarray]:
        """处理完整文件，返回帧 IQ 波形列表。

        Args:
            data: 原始文件字节。

        Returns:
            每个元素为一帧的完整 IQ 波形。
        """
        chunks = chunk_file_with_metadata(data, self.file_id, self.block_size)
        frames = []
        for fid, seq, total, payload in chunks:
            meta = FrameMetadata(
                protocol_version=1,
                file_id=fid,
                session_id=self.session_id,
                block_sequence=seq,
                total_blocks=total,
                payload_length=len(payload),
                profile_id=self.profile_id,
            )
            frame_iq = build_frame(
                payload=payload,
                metadata=meta,
                modulation=self.modulation,
                fec_type=self.fec_type,
                samples_per_symbol=self.samples_per_symbol,
                rolloff=self.rolloff,
                span=self.span,
                interleave_block_size=self.interleave_block_size,
                preamble_length_symbols=self.preamble_length_symbols,
                guard_length_symbols=self.guard_length_symbols,
            )
            frames.append(frame_iq)
        return frames

    def concat_frames(self, frames: list[np.ndarray], inter_frame_gap_samples: int = 0) -> np.ndarray:
        """拼接多帧为连续 IQ 流。

        Args:
            frames: 帧 IQ 波形列表。
            inter_frame_gap_samples: 帧间间隔（零样本数）。

        Returns:
            连续 IQ 波形。
        """
        if not frames:
            return np.array([], dtype=np.complex128)
        if inter_frame_gap_samples == 0:
            return np.concatenate(frames)
        gap = np.zeros(inter_frame_gap_samples, dtype=np.complex128)
        result = [frames[0]]
        for f in frames[1:]:
            result.append(gap)
            result.append(f)
        return np.concatenate(result)
