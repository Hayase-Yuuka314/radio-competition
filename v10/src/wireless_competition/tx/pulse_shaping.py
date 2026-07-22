"""根升余弦 (RRC) 脉冲成形与匹配滤波。

发射端：上采样 + RRC 滤波
接收端：RRC 匹配滤波 + 下采样
"""

from __future__ import annotations

import numpy as np
from scipy import signal


def rrc_filter(
    samples_per_symbol: int,
    rolloff: float = 0.35,
    span: int = 6,
) -> np.ndarray:
    """生成根升余弦滤波器系数。

    Args:
        samples_per_symbol: 每符号采样数。
        rolloff: 滚降因子 α (0 < α ≤ 1)。
        span: 滤波器符号跨度（单侧）。

    Returns:
        RRC 滤波器系数（归一化能量）。
    """
    t = np.arange(-span, span + 1e-9, 1.0 / samples_per_symbol)
    # 避免除零
    t_safe = np.where(np.abs(t) < 1e-12, 1e-12, t)
    pi_t_T = np.pi * t_safe
    four_alpha_t = 4 * rolloff * t_safe

    numerator = np.sin(pi_t_T * (1 - rolloff)) + 4 * rolloff * t_safe * np.cos(pi_t_T * (1 + rolloff))
    denominator = pi_t_T * (1 - (four_alpha_t) ** 2)

    # 处理 t=0 和 t=±T/(4α) 处
    h = np.zeros_like(t)
    mask_normal = np.abs(denominator) > 1e-12
    h[mask_normal] = numerator[mask_normal] / denominator[mask_normal]

    # t=0
    idx_zero = np.argmin(np.abs(t))
    h[idx_zero] = 1.0 - rolloff + 4 * rolloff / np.pi

    # t=±T/(4α)
    t_special = 1.0 / (4 * rolloff)
    idx_special = np.where(np.abs(np.abs(t) - t_special) < 1e-6)[0]
    for idx in idx_special:
        sign = 1 if t[idx] > 0 else -1
        h[idx] = (rolloff / np.sqrt(2)) * (
            (1 + 2 / np.pi) * np.sin(np.pi / (4 * rolloff))
            + (1 - 2 / np.pi) * np.cos(np.pi / (4 * rolloff))
        )

    # 归一化能量
    energy = np.sum(np.abs(h) ** 2)
    if energy > 0:
        h = h / np.sqrt(energy)

    return h.astype(np.float64)


def upsample(symbols: np.ndarray, samples_per_symbol: int) -> np.ndarray:
    """上采样：在符号间插入零。

    Args:
        symbols: 复数符号数组。
        samples_per_symbol: 每符号采样数。

    Returns:
        上采样后数组，长度为 len(symbols) * samples_per_symbol。
    """
    n = len(symbols)
    up = np.zeros(n * samples_per_symbol, dtype=symbols.dtype)
    up[::samples_per_symbol] = symbols
    return up


def pulse_shape(
    symbols: np.ndarray,
    samples_per_symbol: int,
    rolloff: float = 0.35,
    span: int = 6,
) -> np.ndarray:
    """发射端脉冲成形：上采样 + RRC 卷积。

    Args:
        symbols: 复数符号数组。
        samples_per_symbol: 每符号采样数。
        rolloff: 滚降因子。
        span: 滤波器符号跨度。

    Returns:
        基带 IQ 波形。
    """
    rrc = rrc_filter(samples_per_symbol, rolloff, span)
    up = upsample(symbols, samples_per_symbol)
    # 使用 'same' 保持长度一致，加上 = 保证因果性
    shaped = np.convolve(up, rrc, mode='full')
    # 截断到有效长度
    delay = span * samples_per_symbol
    # 返回完整的卷积结果（含滤波器延迟）
    return shaped


def matched_filter(
    iq_signal: np.ndarray,
    samples_per_symbol: int,
    rolloff: float = 0.35,
    span: int = 6,
) -> np.ndarray:
    """接收端匹配滤波：RRC 卷积 + 下采样。

    Args:
        iq_signal: 接收的基带 IQ 波形。
        samples_per_symbol: 每符号采样数。
        rolloff: 滚降因子。
        span: 滤波器符号跨度。

    Returns:
        匹配滤波后的 IQ 波形（与输入同长度）。
    """
    rrc = rrc_filter(samples_per_symbol, rolloff, span)
    mf = np.convolve(iq_signal, rrc, mode='full')
    # 截断：去掉首尾的滤波器暂态
    delay = span * samples_per_symbol
    return mf[delay:-delay] if len(mf) > 2 * delay else mf


def downsample(
    iq_signal: np.ndarray,
    samples_per_symbol: int,
    timing_offset: int = 0,
) -> np.ndarray:
    """从匹配滤波输出中下采样到符号率。

    Args:
        iq_signal: 匹配滤波后的 IQ 波形。
        samples_per_symbol: 每符号采样数。
        timing_offset: 采样级定时偏移。

    Returns:
        符号率复数数组。
    """
    start = timing_offset % samples_per_symbol
    return iq_signal[start::samples_per_symbol]
