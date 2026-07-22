"""多径信道模块。

支持 FIR 多径信道模拟。
"""

from __future__ import annotations

import numpy as np


def apply_multipath(
    iq: np.ndarray,
    taps: list[complex],
    delays_samples: list[int] | None = None,
) -> np.ndarray:
    """施加多径 FIR 信道。

    Args:
        iq: 输入 IQ 数组。
        taps: 复信道冲激响应系数。
        delays_samples: 各径延迟（样本数）。None 表示等间距 1 样本。

    Returns:
        多径信道输出（长度与输入相同）。
    """
    if not taps:
        return iq.copy()

    if delays_samples is None:
        delays_samples = list(range(len(taps)))

    # 构建 FIR 滤波器
    max_delay = max(delays_samples)
    fir = np.zeros(max_delay + 1, dtype=np.complex128)
    for tap, delay in zip(taps, delays_samples):
        fir[delay] += tap

    result = np.convolve(iq, fir, mode='full')
    return result[:len(iq)]


def rayleigh_taps(
    n_taps: int = 4,
    power_delay_profile: list[float] | None = None,
    rng: np.random.Generator | None = None,
) -> list[complex]:
    """生成 Rayleigh 衰落信道抽头。

    Args:
        n_taps: 抽头数。
        power_delay_profile: 各径平均功率（若为 None 使用指数衰减）。
        rng: 随机数生成器。

    Returns:
        复信道抽头列表。
    """
    if rng is None:
        rng = np.random.default_rng()

    if power_delay_profile is None:
        # 指数衰减
        power_delay_profile = [np.exp(-i) for i in range(n_taps)]

    taps = []
    for p in power_delay_profile[:n_taps]:
        std = np.sqrt(p / 2)
        tap = std * (rng.standard_normal() + 1j * rng.standard_normal())
        taps.append(tap)

    return taps
