"""调制与解调模块。

支持 BPSK 和 QPSK 的符号映射、硬/软判决解调。
"""

from __future__ import annotations

import numpy as np


def bytes_to_bits(data: bytes) -> np.ndarray:
    """将字节序列转为比特数组（MSB 优先）。

    Args:
        data: 输入字节。

    Returns:
        uint8 数组，每个元素 0 或 1。
    """
    bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))
    return bits.astype(np.uint8)


def bits_to_bytes(bits: np.ndarray) -> bytes:
    """将比特数组转回字节序列（MSB 优先）。

    不足 8 比特时补零。
    """
    bits_arr = np.asarray(bits, dtype=np.uint8).flatten()
    # 补齐到 8 的倍数
    remainder = len(bits_arr) % 8
    if remainder != 0:
        bits_arr = np.concatenate([bits_arr, np.zeros(8 - remainder, dtype=np.uint8)])
    return np.packbits(bits_arr).tobytes()


def bpsk_modulate(bits: np.ndarray) -> np.ndarray:
    """BPSK 调制：0 → +1, 1 → -1。

    Args:
        bits: uint8 数组，0 或 1。

    Returns:
        复数符号数组。
    """
    bits_arr = np.asarray(bits, dtype=np.float64)
    # 映射：0 → +1, 1 → -1
    symbols = 1.0 - 2.0 * bits_arr
    return symbols.astype(np.complex128)


def bpsk_demodulate_hard(symbols: np.ndarray) -> np.ndarray:
    """BPSK 硬判决解调。

    Args:
        symbols: 复数符号数组。

    Returns:
        uint8 比特数组。
    """
    # 判决：实部 > 0 → 0, 实部 <= 0 → 1
    bits = (np.real(symbols) <= 0).astype(np.uint8)
    return bits


def bpsk_demodulate_soft(symbols: np.ndarray, noise_std: float = 1.0) -> np.ndarray:
    """BPSK 软判决（LLR）。

    LLR = 2 * real(symbol) / sigma^2

    Args:
        symbols: 复数符号数组。
        noise_std: 噪声标准差。

    Returns:
        LLR 数组（正值表示比特更可能是 0）。
    """
    # 避免除零
    sigma2 = max(noise_std ** 2, 1e-12)
    llr = 2.0 * np.real(symbols) / sigma2
    return llr


def qpsk_modulate(bits: np.ndarray) -> np.ndarray:
    """QPSK 调制（Gray 编码）。

    映射：
      00 →  (1+1j)/√2
      01 →  (1-1j)/√2
      11 → (-1-1j)/√2
      10 → (-1+1j)/√2

    Args:
        bits: uint8 数组，长度必须为偶数。

    Returns:
        复数符号数组。
    """
    bits_arr = np.asarray(bits, dtype=np.uint8).flatten()
    if len(bits_arr) % 2 != 0:
        raise ValueError(f"QPSK requires even number of bits, got {len(bits_arr)}")

    # 分组
    even = bits_arr[0::2]   # I 路
    odd = bits_arr[1::2]    # Q 路

    # Gray 映射
    i_part = 1.0 - 2.0 * even.astype(np.float64)   # 0→+1, 1→-1
    q_part = 1.0 - 2.0 * odd.astype(np.float64)

    symbols = (i_part + 1j * q_part) / np.sqrt(2)
    return symbols.astype(np.complex128)


def qpsk_demodulate_hard(symbols: np.ndarray) -> np.ndarray:
    """QPSK 硬判决解调（Gray 解码）。

    Args:
        symbols: 复数符号数组。

    Returns:
        uint8 比特数组（长度为符号数×2）。
    """
    real = np.real(symbols)
    imag = np.imag(symbols)

    even = (real <= 0).astype(np.uint8)    # I 路
    odd = (imag <= 0).astype(np.uint8)     # Q 路

    # 交织
    bits = np.empty(len(symbols) * 2, dtype=np.uint8)
    bits[0::2] = even
    bits[1::2] = odd
    return bits


def qpsk_demodulate_soft(symbols: np.ndarray, noise_std: float = 1.0) -> np.ndarray:
    """QPSK 软判决（LLR）。

    Args:
        symbols: 复数符号数组。
        noise_std: 噪声标准差。

    Returns:
        LLR 数组（偶位置为 I 路，奇位置为 Q 路）。
    """
    sigma2 = max(noise_std ** 2, 1e-12)
    real = np.real(symbols) * np.sqrt(2)
    imag = np.imag(symbols) * np.sqrt(2)

    llr_i = 2.0 * real / sigma2
    llr_q = 2.0 * imag / sigma2

    llr = np.empty(len(symbols) * 2, dtype=np.float64)
    llr[0::2] = llr_i
    llr[1::2] = llr_q
    return llr
