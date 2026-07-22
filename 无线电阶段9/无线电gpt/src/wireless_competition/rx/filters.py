"""接收端滤波器。

包括自适应陷波器和带通滤波器。
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfilt, iirnotch


def apply_notch_filter(
    iq_signal: np.ndarray,
    notch_freq_hz: float,
    sample_rate_hz: float,
    quality_factor: float = 30.0,
) -> np.ndarray:
    """应用 IIR 陷波器。

    Args:
        iq_signal: 输入 IQ 信号。
        notch_freq_hz: 陷波中心频率 (Hz)。
        sample_rate_hz: 采样率。
        quality_factor: Q 值。

    Returns:
        陷波后信号。
    """
    nyq = sample_rate_hz / 2
    w0 = notch_freq_hz / nyq
    if not (0 < w0 < 1):
        return iq_signal

    b, a = iirnotch(w0, quality_factor)
    filtered = sosfilt(
        np.array([[b[0], b[1], b[2], 1.0, a[1], a[2]]]),
        iq_signal,
    )
    return filtered


def apply_bandpass_filter(
    iq_signal: np.ndarray,
    low_hz: float,
    high_hz: float,
    sample_rate_hz: float,
    order: int = 4,
) -> np.ndarray:
    """应用 Butterworth 带通滤波器。

    Args:
        iq_signal: 输入 IQ 信号。
        low_hz: 低截止频率。
        high_hz: 高截止频率。
        sample_rate_hz: 采样率。
        order: 滤波器阶数。

    Returns:
        滤波后信号。
    """
    nyq = sample_rate_hz / 2
    low = max(0.001, low_hz / nyq)
    high = min(0.999, high_hz / nyq)
    sos = butter(order, [low, high], btype="band", output="sos")
    return sosfilt(sos, iq_signal)
