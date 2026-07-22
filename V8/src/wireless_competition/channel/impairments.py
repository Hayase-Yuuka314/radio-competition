"""信道硬件损伤模块。

包括 CFO、DC 偏移、IQ 不平衡、相位噪声、量化、削顶和丢样。
"""

from __future__ import annotations

import numpy as np

from ..common.validation import check_finite


def apply_cfo(
    iq: np.ndarray,
    cfo_hz: float,
    sample_rate_hz: float,
) -> np.ndarray:
    """施加载波频率偏移。

    Args:
        iq: 输入 IQ 数组。
        cfo_hz: CFO (Hz)。
        sample_rate_hz: 采样率 (Hz)。

    Returns:
        频偏后的 IQ 数组。
    """
    check_finite(iq, "iq")
    n = len(iq)
    t = np.arange(n) / sample_rate_hz
    rotation = np.exp(1j * 2 * np.pi * cfo_hz * t)
    return iq * rotation.astype(np.complex128)


def apply_sro(
    iq: np.ndarray,
    sro_ppm: float,
    sample_rate_hz: float,
    original_sample_rate_hz: float | None = None,
) -> np.ndarray:
    """模拟采样时钟偏差 (SRO) 通过重采样。

    Args:
        iq: 输入 IQ 数组。
        sro_ppm: 采样率偏差 (ppm)。
        sample_rate_hz: 原始采样率。
        original_sample_rate_hz: 发射端采样率（默认等于 sample_rate_hz）。

    Returns:
        重采样后的 IQ 数组。
    """
    from scipy import signal as sp_signal

    if original_sample_rate_hz is None:
        original_sample_rate_hz = sample_rate_hz

    true_rate = original_sample_rate_hz * (1 + sro_ppm / 1e6)
    ratio = true_rate / sample_rate_hz
    n = len(iq)
    n_new = max(1, int(n / ratio))
    resampled = sp_signal.resample(iq, n_new)
    return resampled


def apply_timing_offset(
    iq: np.ndarray,
    offset_symbols: float,
    samples_per_symbol: int,
) -> np.ndarray:
    """施加分数符号定时偏移。

    通过整数样本移位 + 线性插值实现。

    Args:
        iq: 输入 IQ 数组（已上采样）。
        offset_symbols: 偏移量（符号数）。
        samples_per_symbol: 每符号采样数。

    Returns:
        移位后的 IQ 数组。
    """
    offset_samples = offset_symbols * samples_per_symbol
    int_part = int(np.floor(offset_samples))
    frac = offset_samples - int_part

    # 整数移位
    if int_part > 0:
        shifted = np.concatenate([np.zeros(int_part, dtype=iq.dtype), iq])
    elif int_part < 0:
        shifted = iq[-int_part:]
    else:
        shifted = iq.copy()

    # 分数延迟（线性插值）
    if abs(frac) > 1e-9:
        shifted = (1 - frac) * shifted + frac * np.concatenate([[0], shifted[:-1]])

    return shifted


def apply_dc_offset(
    iq: np.ndarray,
    dc: complex = 0.05 + 0.03j,
) -> np.ndarray:
    """施加 DC 偏移。"""
    return iq + dc


def apply_iq_imbalance(
    iq: np.ndarray,
    gain_imbalance_db: float = 1.0,
    phase_imbalance_deg: float = 5.0,
) -> np.ndarray:
    """施加 IQ 不平衡。

    Args:
        iq: 输入 IQ 数组。
        gain_imbalance_db: I/Q 增益差 (dB)。
        phase_imbalance_deg: I/Q 相位偏差 (度)。

    Returns:
        不平衡后的 IQ。
    """
    i_part = np.real(iq)
    q_part = np.imag(iq)

    gain_linear = 10 ** (gain_imbalance_db / 20)
    phase_rad = np.deg2rad(phase_imbalance_deg)

    # I 路放大
    i_imbalanced = gain_linear * i_part
    # Q 路相位旋转
    q_imbalanced = i_part * np.sin(phase_rad) + q_part * np.cos(phase_rad)

    return (i_imbalanced + 1j * q_imbalanced).astype(np.complex128)


def apply_phase_noise(
    iq: np.ndarray,
    std_rad: float = 0.01,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """施加相位噪声（维纳过程）。

    Args:
        iq: 输入 IQ 数组。
        std_rad: 每样本相位噪声标准差 (rad)。
        rng: 随机数生成器。

    Returns:
        含相位噪声的 IQ。
    """
    if rng is None:
        rng = np.random.default_rng()
    n = len(iq)
    phase_steps = rng.normal(0, std_rad, n)
    phase = np.cumsum(phase_steps)
    return iq * np.exp(1j * phase).astype(np.complex128)


def apply_clipping(
    iq: np.ndarray,
    threshold: float = 1.0,
) -> np.ndarray:
    """硬削顶。

    Args:
        iq: 输入 IQ 数组。
        threshold: 幅度阈值。

    Returns:
        削顶后的 IQ。
    """
    mag = np.abs(iq)
    result = iq.copy()
    mask = mag > threshold
    result[mask] = threshold * result[mask] / mag[mask]
    return result


def apply_quantization(
    iq: np.ndarray,
    bits: int = 12,
    full_scale: float = 1.0,
) -> np.ndarray:
    """模拟 ADC 量化。

    Args:
        iq: 输入 IQ 数组。
        bits: 量化位宽。
        full_scale: 满量程范围 [-full_scale, full_scale]。

    Returns:
        量化后的 IQ。
    """
    levels = 2 ** (bits - 1) - 1
    real = np.clip(np.real(iq), -full_scale, full_scale)
    imag = np.clip(np.imag(iq), -full_scale, full_scale)
    real_q = np.round(real * levels) / levels
    imag_q = np.round(imag * levels) / levels
    return (real_q + 1j * imag_q).astype(np.complex128)


def apply_drop_samples(
    iq: np.ndarray,
    drop_probability: float = 0.01,
    rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """随机丢样。

    Args:
        iq: 输入 IQ 数组。
        drop_probability: 每个样本的丢弃概率。
        rng: 随机数生成器。

    Returns:
        (保留的 IQ 数组, 丢弃位置的布尔掩码)。
    """
    if rng is None:
        rng = np.random.default_rng()
    n = len(iq)
    keep_mask = rng.random(n) > drop_probability
    return iq[keep_mask], ~keep_mask
