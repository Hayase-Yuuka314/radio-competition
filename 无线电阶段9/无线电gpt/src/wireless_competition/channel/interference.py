"""干扰生成模块。

支持单音、多音、扫频、宽带噪声、带限噪声、突发噪声和数字干扰。
"""

from __future__ import annotations

import numpy as np


def tone_interference(
    n_samples: int,
    frequency_hz: float,
    sample_rate_hz: float,
    amplitude: float = 1.0,
    phase: float = 0.0,
) -> np.ndarray:
    """单音干扰。"""
    t = np.arange(n_samples) / sample_rate_hz
    return amplitude * np.exp(1j * (2 * np.pi * frequency_hz * t + phase)).astype(np.complex128)


def multitone_interference(
    n_samples: int,
    frequencies_hz: list[float],
    sample_rate_hz: float,
    amplitudes: list[float] | None = None,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """多音干扰。"""
    if rng is None:
        rng = np.random.default_rng()
    if amplitudes is None:
        amplitudes = [1.0] * len(frequencies_hz)

    t = np.arange(n_samples) / sample_rate_hz
    result = np.zeros(n_samples, dtype=np.complex128)
    for f, amp in zip(frequencies_hz, amplitudes):
        phase = rng.uniform(0, 2 * np.pi)
        result += amp * np.exp(1j * (2 * np.pi * f * t + phase))
    return result


def sweep_interference(
    n_samples: int,
    sample_rate_hz: float,
    f_start_hz: float,
    f_end_hz: float,
    amplitude: float = 1.0,
) -> np.ndarray:
    """线性扫频干扰 (chirp)。"""
    t = np.arange(n_samples) / sample_rate_hz
    k = (f_end_hz - f_start_hz) / (n_samples / sample_rate_hz)
    phase = 2 * np.pi * (f_start_hz * t + 0.5 * k * t ** 2)
    return amplitude * np.exp(1j * phase).astype(np.complex128)


def broadband_noise(
    n_samples: int,
    power: float = 1.0,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """宽带高斯噪声干扰。"""
    if rng is None:
        rng = np.random.default_rng()
    noise = rng.standard_normal(n_samples) + 1j * rng.standard_normal(n_samples)
    noise_power = np.mean(np.abs(noise) ** 2)
    return noise * np.sqrt(power / noise_power)


def bandlimited_noise(
    n_samples: int,
    sample_rate_hz: float,
    center_hz: float,
    bandwidth_hz: float,
    power: float = 1.0,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """带限噪声干扰。"""
    from scipy.signal import butter, sosfilt

    if rng is None:
        rng = np.random.default_rng()

    # 生成白噪声
    noise = broadband_noise(n_samples, power, rng)

    # 带通滤波
    nyq = sample_rate_hz / 2
    low = max(0.001, (center_hz - bandwidth_hz / 2) / nyq)
    high = min(0.999, (center_hz + bandwidth_hz / 2) / nyq)
    if low >= high:
        high = min(0.999, low + 0.01)  # 兜底
    sos = butter(4, [low, high], btype="band", output="sos")
    filtered = sosfilt(sos, noise)

    # 重新调整功率
    filtered_power = np.mean(np.abs(filtered) ** 2)
    if filtered_power > 0:
        filtered = filtered * np.sqrt(power / filtered_power)

    return filtered.astype(np.complex128)


def burst_noise(
    n_samples: int,
    power: float = 1.0,
    burst_duty_cycle: float = 0.2,
    burst_length_samples: int = 1000,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """突发噪声干扰。

    按 burst_length 周期随机出现 burst_duty_cycle 比的噪声。
    """
    if rng is None:
        rng = np.random.default_rng()

    result = np.zeros(n_samples, dtype=np.complex128)
    pos = 0
    while pos < n_samples:
        if rng.random() < burst_duty_cycle:
            end = min(pos + burst_length_samples, n_samples)
            noise = rng.standard_normal(end - pos) + 1j * rng.standard_normal(end - pos)
            noise_power_val = np.mean(np.abs(noise) ** 2)
            if noise_power_val > 0:
                noise = noise * np.sqrt(power / noise_power_val)
            result[pos:end] = noise
        pos += burst_length_samples

    return result


def generate_interference(
    n_samples: int,
    sample_rate_hz: float,
    interference_type: str = "tone",
    inr_db: float = 10.0,
    signal_power: float = 1.0,
    frequency_hz: float | None = None,
    bandwidth_hz: float | None = None,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """统一干扰生成接口。

    Args:
        n_samples: 样本数。
        sample_rate_hz: 采样率。
        interference_type: 干扰类型。
        inr_db: 干噪比 (干扰功率/噪声功率)。
        signal_power: 信号功率（用于功率标定）。
        frequency_hz: 中心频率。
        bandwidth_hz: 带宽。
        rng: 随机数生成器。

    Returns:
        干扰 IQ 数组。
    """
    if rng is None:
        rng = np.random.default_rng()

    # 干扰功率（线性）
    interference_power = signal_power * (10 ** (inr_db / 10))

    if frequency_hz is None:
        frequency_hz = sample_rate_hz * 0.1  # 默认频偏 10%

    if bandwidth_hz is None:
        bandwidth_hz = sample_rate_hz * 0.01

    if interference_type == "tone":
        return tone_interference(n_samples, frequency_hz, sample_rate_hz,
                                 amplitude=np.sqrt(interference_power))
    elif interference_type == "multitone":
        freqs = [frequency_hz, frequency_hz * 1.5, frequency_hz * 2.0]
        amps = [np.sqrt(interference_power / 3)] * 3
        return multitone_interference(n_samples, freqs, sample_rate_hz, amps, rng)
    elif interference_type == "sweep":
        return sweep_interference(n_samples, sample_rate_hz,
                                  frequency_hz - bandwidth_hz,
                                  frequency_hz + bandwidth_hz,
                                  amplitude=np.sqrt(interference_power))
    elif interference_type == "broadband_noise":
        return broadband_noise(n_samples, interference_power, rng)
    elif interference_type == "bandlimited_noise":
        return bandlimited_noise(n_samples, sample_rate_hz, frequency_hz,
                                 bandwidth_hz, interference_power, rng)
    elif interference_type == "burst":
        return burst_noise(n_samples, interference_power, rng=rng)
    else:
        return np.zeros(n_samples, dtype=np.complex128)
