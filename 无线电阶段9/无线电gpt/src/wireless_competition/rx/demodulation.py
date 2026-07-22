"""解调器模块。

整合 BPSK/QPSK 硬/软判决解调。
"""

from __future__ import annotations

import numpy as np

from ..common.types import ModulationType


def demodulate_hard(
    symbols: np.ndarray,
    modulation: ModulationType = ModulationType.BPSK,
) -> np.ndarray:
    """硬判决解调。

    Args:
        symbols: 复数符号数组。
        modulation: 调制类型。

    Returns:
        uint8 比特数组。
    """
    from ..tx.modulation import bpsk_demodulate_hard, qpsk_demodulate_hard

    if modulation == ModulationType.BPSK:
        return bpsk_demodulate_hard(symbols)
    elif modulation == ModulationType.QPSK:
        return qpsk_demodulate_hard(symbols)
    else:
        raise ValueError(f"Unknown modulation: {modulation}")


def demodulate_soft(
    symbols: np.ndarray,
    modulation: ModulationType = ModulationType.BPSK,
    noise_std: float = 1.0,
) -> np.ndarray:
    """软判决解调（LLR）。

    Args:
        symbols: 复数符号数组。
        modulation: 调制类型。
        noise_std: 噪声标准差估计。

    Returns:
        LLR 数组。
    """
    from ..tx.modulation import bpsk_demodulate_soft, qpsk_demodulate_soft

    if modulation == ModulationType.BPSK:
        return bpsk_demodulate_soft(symbols, noise_std)
    elif modulation == ModulationType.QPSK:
        return qpsk_demodulate_soft(symbols, noise_std)
    else:
        raise ValueError(f"Unknown modulation: {modulation}")


def estimate_noise_std(symbols: np.ndarray, modulation: ModulationType = ModulationType.BPSK) -> float:
    """从解调符号估计噪声标准差（基于 EVM）。

    Args:
        symbols: 复数符号数组。
        modulation: 调制类型。

    Returns:
        噪声标准差估计。
    """
    from ..tx.modulation import bpsk_demodulate_hard, qpsk_demodulate_hard

    if modulation == ModulationType.BPSK:
        # BPSK: 理想符号在 ±1
        bits = bpsk_demodulate_hard(symbols)
        ideal = 1.0 - 2.0 * bits.astype(np.float64)
        errors = np.real(symbols) - ideal
    elif modulation == ModulationType.QPSK:
        bits = qpsk_demodulate_hard(symbols)
        even = 1.0 - 2.0 * bits[0::2].astype(np.float64)
        odd = 1.0 - 2.0 * bits[1::2].astype(np.float64)
        ideal = (even + 1j * odd) / np.sqrt(2)
        errors = np.real(symbols - ideal)
    else:
        return 1.0

    return float(np.std(np.real(errors)) * np.sqrt(2))


def compute_evm(
    symbols: np.ndarray,
    modulation: ModulationType = ModulationType.BPSK,
) -> float:
    """计算误差矢量幅度 (EVM)。

    Returns:
        EVM (线性比例)。
    """
    from ..tx.modulation import bpsk_demodulate_hard, qpsk_demodulate_hard

    if modulation == ModulationType.BPSK:
        bits = bpsk_demodulate_hard(symbols)
        ideal = (1.0 - 2.0 * bits.astype(np.float64)).astype(np.complex128)
    elif modulation == ModulationType.QPSK:
        bits = qpsk_demodulate_hard(symbols)
        even = 1.0 - 2.0 * bits[0::2].astype(np.float64)
        odd = 1.0 - 2.0 * bits[1::2].astype(np.float64)
        ideal = ((even + 1j * odd) / np.sqrt(2)).astype(np.complex128)
    else:
        return float("nan")

    if len(symbols) != len(ideal):
        return float("nan")

    error = symbols - ideal
    rms_error = np.sqrt(np.mean(np.abs(error) ** 2))
    ref_power = np.sqrt(np.mean(np.abs(ideal) ** 2))

    return float(rms_error / ref_power) if ref_power > 0 else float("inf")
