"""块交织器/去交织器。

应对突发干扰，将连续比特分散到不同位置。
"""

from __future__ import annotations

import numpy as np


def block_interleave(bits: np.ndarray, block_size: int) -> np.ndarray:
    """按行写入、按列读出的块交织。

    Args:
        bits: 一维比特数组。
        block_size: 列数（即每行长度）。

    Returns:
        交织后的比特数组。不足整块的部分不处理。
    """
    bits = np.asarray(bits, dtype=bits.dtype).flatten()
    n = len(bits)

    # 完整块数
    n_full = (n // block_size) * block_size
    if n_full == 0:
        return bits.copy()

    # 重塑为 (rows, block_size)，按列读出
    reshaped = bits[:n_full].reshape(-1, block_size)
    interleaved = reshaped.T.flatten()

    # 尾块不处理
    if n > n_full:
        interleaved = np.concatenate([interleaved, bits[n_full:]])

    return interleaved


def block_deinterleave(bits: np.ndarray, block_size: int) -> np.ndarray:
    """块交织的逆操作：按列写入、按行读出。

    Args:
        bits: 交织后的比特数组。
        block_size: 交织时的列数。

    Returns:
        去交织后的比特数组。
    """
    bits = np.asarray(bits, dtype=bits.dtype).flatten()
    n = len(bits)

    n_full = (n // block_size) * block_size
    if n_full == 0:
        return bits.copy()

    rows = n_full // block_size
    # 按列写入
    reshaped = bits[:n_full].reshape(block_size, rows).T
    deinterleaved = reshaped.flatten()

    if n > n_full:
        deinterleaved = np.concatenate([deinterleaved, bits[n_full:]])

    return deinterleaved


def random_interleave(
    bits: np.ndarray,
    seed: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """随机交织（固定排列）。

    Args:
        bits: 输入比特数组。
        seed: 排列种子。

    Returns:
        (交织后比特, 排列索引数组)。
    """
    rng = np.random.default_rng(seed)
    n = len(bits)
    perm = rng.permutation(n)
    return bits[perm], perm


def random_deinterleave(
    bits: np.ndarray,
    perm: np.ndarray,
) -> np.ndarray:
    """随机交织的逆操作。"""
    n = len(bits)
    inv_perm = np.argsort(perm)
    return bits[inv_perm]
