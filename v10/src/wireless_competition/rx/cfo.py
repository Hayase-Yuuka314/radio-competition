"""载波频率偏移 (CFO) 估计与校正。

使用前导或导频估计频偏。
"""

from __future__ import annotations

import numpy as np


def estimate_cfo_from_preamble(
    iq_signal: np.ndarray,
    preamble: np.ndarray,
    samples_per_symbol: int,
    sample_rate_hz: float,
) -> float:
    """从已知前导估计 CFO。

    方法：计算前导接收信号与本地副本的相位差变化率。

    Args:
        iq_signal: 接收 IQ 波形（从帧起始开始）。
        preamble: 前导符号（未上采样）。
        samples_per_symbol: 每符号采样数。
        sample_rate_hz: 采样率。

    Returns:
        CFO 估计 (Hz)。
    """
    preamble_len = len(preamble)

    # 提取前导区域（符号率）
    if len(iq_signal) < preamble_len * samples_per_symbol:
        return 0.0

    # 下采样到符号率（粗略定时）
    sym_signal = iq_signal[::samples_per_symbol][:preamble_len]

    if len(sym_signal) < 2:
        return 0.0

    # 逐符号相位差
    phase_diff = np.angle(sym_signal[1:] * np.conj(preamble[1:]) *
                          np.conj(sym_signal[:-1]) * preamble[:-1])

    # 平均相位差 → CFO
    mean_phase_diff = np.mean(phase_diff)
    cfo_hz = mean_phase_diff * sample_rate_hz / (2 * np.pi * samples_per_symbol)

    return float(cfo_hz)


def correct_cfo(
    iq_signal: np.ndarray,
    cfo_hz: float,
    sample_rate_hz: float,
) -> np.ndarray:
    """校正 CFO（逆旋转）。

    Args:
        iq_signal: 接收 IQ 波形。
        cfo_hz: CFO 估计 (Hz)。
        sample_rate_hz: 采样率。

    Returns:
        频偏校正后的 IQ。
    """
    n = len(iq_signal)
    t = np.arange(n) / sample_rate_hz
    correction = np.exp(-1j * 2 * np.pi * cfo_hz * t)
    return iq_signal * correction.astype(np.complex128)


def estimate_cfo_from_pilots(
    symbols: np.ndarray,
    pilot_spacing: int = 16,
    sample_rate_hz: float = 1.0,
) -> float:
    """从导频符号估计残余 CFO。

    Args:
        symbols: 接收符号（符号率）。
        pilot_spacing: 导频间距。
        sample_rate_hz: 符号率。

    Returns:
        残余 CFO 估计 (Hz)。
    """
    n = len(symbols)
    if n < pilot_spacing * 2:
        return 0.0

    # 取相隔 pilot_spacing 的符号对
    phase_diffs = []
    for i in range(0, n - pilot_spacing, pilot_spacing):
        # 假设导频已知（这里简化：相邻导频符号相同）
        phase_diff = np.angle(symbols[i + pilot_spacing] * np.conj(symbols[i]))
        phase_diffs.append(phase_diff)

    if not phase_diffs:
        return 0.0

    mean_phase_diff = np.mean(phase_diffs)
    cfo_hz = mean_phase_diff * sample_rate_hz / (2 * np.pi * pilot_spacing)

    return float(cfo_hz)
