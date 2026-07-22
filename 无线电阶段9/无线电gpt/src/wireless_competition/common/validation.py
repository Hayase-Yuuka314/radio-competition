"""输入校验工具。

提供参数合法性检查和边界验证，防止 NaN/Inf、数组越界等问题。
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def check_finite(arr: np.ndarray, name: str = "array") -> None:
    """检查数组中无 NaN 或 Inf。

    Raises:
        ValueError: 如果存在非有限值。
    """
    if not np.all(np.isfinite(arr)):
        n_nan = int(np.sum(np.isnan(arr)))
        n_inf = int(np.sum(np.isinf(arr)))
        raise ValueError(
            f"{name}: {n_nan} NaN and {n_inf} Inf values found "
            f"in array of shape {arr.shape}"
        )


def check_shape(
    arr: np.ndarray,
    expected: tuple[int, ...],
    name: str = "array",
    allow_broadcast: bool = False,
) -> None:
    """检查数组维度。

    Raises:
        ValueError: 如果维度不匹配。
    """
    if not allow_broadcast and arr.ndim != len(expected):
        raise ValueError(
            f"{name}: expected {len(expected)}D array, got {arr.ndim}D (shape {arr.shape})"
        )
    if arr.ndim == len(expected):
        for i, (actual, exp) in enumerate(zip(arr.shape, expected)):
            if exp is not None and exp >= 0 and actual != exp:
                raise ValueError(
                    f"{name}: axis {i} expected size {exp}, got {actual}"
                )


def check_positive(value: float, name: str = "value") -> None:
    """检查数值为正。"""
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")


def check_nonnegative(value: float, name: str = "value") -> None:
    """检查数值非负。"""
    if value < 0:
        raise ValueError(f"{name} must be non-negative, got {value}")


def check_probability(value: float, name: str = "probability") -> None:
    """检查值在 [0, 1] 范围内。"""
    if not (0.0 <= value <= 1.0):
        raise ValueError(f"{name} must be in [0, 1], got {value}")


def check_nyquist(
    sample_rate_hz: float,
    max_freq_hz: float,
    name: str = "frequency",
) -> None:
    """检查是否满足 Nyquist 采样定理。"""
    if max_freq_hz > sample_rate_hz / 2:
        raise ValueError(
            f"{name}={max_freq_hz} Hz exceeds Nyquist limit "
            f"({sample_rate_hz / 2} Hz) for sample_rate={sample_rate_hz} Hz"
        )


def check_rf_safety(config: dict[str, Any]) -> list[str]:
    """检查 RF 发射配置的安全性。

    Returns:
        警告/错误列表，空列表表示安全。
    """
    issues: list[str] = []
    rf = config.get("rf", {})

    # 检查关键字段是否为 null
    for key in [
        "allowed_center_frequencies_hz",
        "max_occupied_bandwidth_hz",
        "max_tx_gain_db",
    ]:
        if rf.get(key) is None:
            issues.append(f"RF field '{key}' is null — TX blocked")

    hw = config.get("hardware", {})
    if hw.get("tx_uri") is None:
        issues.append("Hardware TX URI is null — TX blocked")

    return issues
