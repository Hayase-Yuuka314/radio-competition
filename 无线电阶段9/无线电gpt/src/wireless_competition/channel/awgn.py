"""AWGN 信道。

添加加性高斯白噪声。
"""

from __future__ import annotations

import numpy as np

from ..common.validation import check_finite


def add_awgn(
    iq: np.ndarray,
    snr_db: float,
    signal_power: float | None = None,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """添加 AWGN 到 IQ 信号。

    Args:
        iq: 输入复数 IQ 数组。
        snr_db: 信噪比 (dB)。
        signal_power: 信号功率。若为 None，从 iq 估算。
        rng: 随机数生成器。

    Returns:
        加噪后的 IQ 数组。
    """
    check_finite(iq, "iq")
    if rng is None:
        rng = np.random.default_rng()

    if signal_power is None:
        signal_power = np.mean(np.abs(iq) ** 2)

    snr_linear = 10 ** (snr_db / 10)
    noise_power = signal_power / snr_linear

    # 复噪声：每维方差 = noise_power / 2
    noise_std = np.sqrt(noise_power / 2)
    noise = noise_std * (rng.standard_normal(iq.shape) + 1j * rng.standard_normal(iq.shape))

    return iq + noise.astype(np.complex128)
