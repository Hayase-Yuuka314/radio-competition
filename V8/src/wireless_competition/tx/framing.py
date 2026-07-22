"""发射端组帧模块。

构建完整物理层帧：
  | Guard | Preamble | Sync Word | Header | Pilot | Payload | CRC | Guard |

所有字段参数均可配置。
"""

from __future__ import annotations

import numpy as np

from ..common.types import FECType, FrameMetadata, ModulationType, ProfileID
from ..file_protocol.frame_header import encode_header
from ..file_protocol.integrity import append_crc32
from .fec import encode as fec_encode
from .interleaver import block_interleave
from .modulation import bpsk_modulate, bytes_to_bits, qpsk_modulate


# ── 默认序列 ────────────────────────────────────────────────────

def make_preamble(
    samples_per_symbol: int,
    length_symbols: int = 64,
    pattern: str = "pn",
) -> np.ndarray:
    """生成前导符号。

    Args:
        samples_per_symbol: 每符号采样数（仅用于验证）。
        length_symbols: 前导长度（符号数）。
        pattern: 前导模式。"pn" 用于更好的时域相关特性（默认）。

    Returns:
        前导符号（未上采样）复数数组。
    """
    if pattern == "pn":
        # PN 序列（BPSK 随机）：更好的时域相关特性
        rng = np.random.default_rng(42)
        bits = (rng.random(length_symbols) > 0.5).astype(np.uint8)
        return bpsk_modulate(bits)
    elif pattern == "zadoff-chu":
        # Zadoff-Chu 序列，根索引 1
        n = np.arange(length_symbols)
        cf = 1  # ZC 根索引
        zc = np.exp(-1j * np.pi * cf * n * (n + 1) / length_symbols)
        return zc.astype(np.complex128)
    else:
        raise ValueError(f"Unknown preamble pattern: {pattern}")


def make_sync_word() -> np.ndarray:
    """生成同步字（BPSK 符号形式）。

    Returns:
        16 个 BPSK 符号。
    """
    # 固定同步字：0x1ACF (16 bits)
    sync_bits = np.array(
        [0, 0, 0, 1, 1, 0, 1, 0, 1, 1, 0, 0, 1, 1, 1, 1],
        dtype=np.uint8,
    )
    return bpsk_modulate(sync_bits)


def make_guard(samples_per_symbol: int, length_symbols: int = 8) -> np.ndarray:
    """生成保护间隔（符号级零）。

    Args:
        samples_per_symbol: 每符号采样数（保留用于 API 兼容）。
        length_symbols: 保护间隔长度（符号数）。

    Returns:
        复数零数组（符号率），长度 = length_symbols。
    """
    return np.zeros(length_symbols, dtype=np.complex128)


# ── 组帧 ────────────────────────────────────────────────────────


def build_frame(
    payload: bytes,
    metadata: FrameMetadata,
    modulation: ModulationType = ModulationType.BPSK,
    fec_type: FECType = FECType.CONVOLUTIONAL,
    samples_per_symbol: int = 8,
    rolloff: float = 0.35,
    span: int = 6,
    interleave_block_size: int = 0,
    preamble_length_symbols: int = 64,
    guard_length_symbols: int = 16,
) -> np.ndarray:
    """构建完整物理层帧（IQ 波形）。

    帧结构：
        [Guard] [Preamble(未上采样)] [Sync Word] [Header] [Pilot] [Payload+CRC] [Guard]

    其中 Header 和 Pilot 用 BPSK 调制保证鲁棒性。

    Args:
        payload: 有效载荷字节。
        metadata: 帧元数据。
        modulation: 调制方式。
        fec_type: FEC 类型。
        samples_per_symbol: 每符号采样数。
        rolloff: RRC 滚降因子。
        span: RRC 符号跨度。
        interleave_block_size: 交织块大小（0 表示不交织）。
        preamble_length_symbols: 前导长度。
        guard_length_symbols: 保护间隔长度。

    Returns:
        完整帧 IQ 波形（复数数组）。
    """
    from .pulse_shaping import pulse_shape

    sps = samples_per_symbol

    # 1. 编码载荷
    payload_crc = append_crc32(payload)
    payload_bits = bytes_to_bits(payload_crc)
    metadata.payload_length = len(payload)

    # FEC 编码
    encoded_bits = fec_encode(payload_bits, fec_type)
    original_bit_count = len(payload_bits)

    # 交织
    if interleave_block_size > 0:
        encoded_bits = block_interleave(encoded_bits, interleave_block_size)

    # 2. 构建符号级帧
    guard_sym = np.zeros(guard_length_symbols, dtype=np.complex128)
    preamble_sym = make_preamble(sps, preamble_length_symbols)
    sync_sym = make_sync_word()

    # 包头（BPSK）
    header_bytes = encode_header(metadata)
    header_bits = bytes_to_bits(header_bytes)
    # 包头也用 FEC
    header_encoded = fec_encode(header_bits, FECType.CONVOLUTIONAL)
    header_sym = bpsk_modulate(header_encoded)

    # 导频（BPSK）
    pilot_bits = bytes_to_bits(b"\x55" * 16)  # 交替 0/1
    pilot_sym = bpsk_modulate(pilot_bits)

    # 有效载荷符号
    if modulation == ModulationType.BPSK:
        payload_sym = bpsk_modulate(encoded_bits)
    elif modulation == ModulationType.QPSK:
        payload_sym = qpsk_modulate(encoded_bits)
    else:
        raise ValueError(f"Unknown modulation: {modulation}")

    # 拼接符号级帧（不含 guard，guard 在 IQ 采样级添加）
    frame_symbols = np.concatenate([
        preamble_sym,
        sync_sym,
        header_sym,
        pilot_sym,
        payload_sym,
    ])

    # 3. 脉冲成形
    frame_iq = pulse_shape(frame_symbols, sps, rolloff, span)

    # 4. 在 IQ 采样级添加保护间隔（避免符号级 guard 的 ISI 污染前导）
    guard_iq = np.zeros(guard_length_symbols * sps, dtype=np.complex128)
    frame_iq = np.concatenate([guard_iq, frame_iq, guard_iq])

    return frame_iq
