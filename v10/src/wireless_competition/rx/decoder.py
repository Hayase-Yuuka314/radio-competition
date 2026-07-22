"""接收端译码器。

整合 FEC 译码、去交织、CRC 校验。
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from ..common.types import FECType, FailureReason, FrameMetadata, ProfileID
from ..file_protocol.integrity import check_crc32
from ..tx.fec import decode_hard as fec_decode_hard
from ..tx.fec import decode_soft as fec_decode_soft
from ..tx.interleaver import block_deinterleave


class Decoder:
    """接收端译码器。

    组合去交织、FEC 译码和 CRC 校验。
    """

    def __init__(
        self,
        fec_type: FECType = FECType.NONE,
        interleave_block_size: int = 0,
    ):
        self.fec_type = fec_type
        self.interleave_block_size = interleave_block_size

    def decode_bits(
        self,
        bits: np.ndarray,
        original_bit_count: int,
        is_soft: bool = False,
        noise_std: float = 1.0,
    ) -> tuple[np.ndarray, int]:
        """译码比特序列。

        Args:
            bits: 接收比特（硬判决）或 LLR（软判决）。
            original_bit_count: 原始载荷比特数。
            is_soft: 是否为软判决。
            noise_std: 噪声标准差。

        Returns:
            (译码后比特, 译码后错误比特数（硬判决时估计）)。
        """
        # 去交织
        if self.interleave_block_size > 0:
            bits = block_deinterleave(bits, self.interleave_block_size)

        # FEC 译码
        if is_soft:
            decoded = fec_decode_soft(bits, self.fec_type, original_bit_count)
            # 软判决无法统计 bit errors
            raw_errors = -1
        else:
            # 硬判决：先统计原始错误（如果有原始比特参考）
            decoded = fec_decode_hard(bits, self.fec_type, original_bit_count)
            raw_errors = -1  # 在流水线层统计

        return decoded, raw_errors

    def check_payload_crc(self, data_with_crc: bytes) -> tuple[bytes, bool]:
        """校验载荷 CRC-32。"""
        return check_crc32(data_with_crc)
