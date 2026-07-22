"""异常恢复机制。

处理各种运行时异常：模型缺失/SDR断连/NaN/磁盘满等。
每个异常有日志+回退策略，确保系统不崩溃。
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np


def safe_call(
    func: Callable,
    *args,
    fallback: Any = None,
    max_retries: int = 1,
    retry_delay_s: float = 0.5,
    log_fn: Optional[Callable] = None,
    **kwargs,
) -> Any:
    """安全调用：捕获异常 → 重试 → 回退。

    Args:
        func: 要调用的函数。
        *args, **kwargs: 函数参数。
        fallback: 失败时的回退值。
        max_retries: 最大重试次数。
        retry_delay_s: 重试间隔（秒）。
        log_fn: 日志函数 (msg: str) -> None。

    Returns:
        函数返回值或 fallback。
    """
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_error = e
            if log_fn:
                log_fn(f"[recovery] {func.__name__} failed (attempt {attempt+1}): {e}")
            if attempt < max_retries:
                time.sleep(retry_delay_s)

    if log_fn:
        log_fn(f"[recovery] {func.__name__} all retries exhausted, using fallback")
    return fallback() if callable(fallback) else fallback


def check_model_file(path: str | Path) -> tuple[bool, str]:
    """检查模型文件是否存在且可读。

    Returns:
        (是否可用, 原因描述)。
    """
    path = Path(path)
    if not path.exists():
        return False, f"Model file not found: {path}"
    if not path.is_file():
        return False, f"Path is not a file: {path}"
    if path.stat().st_size == 0:
        return False, f"Model file is empty: {path}"
    return True, "ok"


def check_disk_space(path: str | Path, min_free_gb: float = 1.0) -> tuple[bool, str]:
    """检查磁盘剩余空间。

    Returns:
        (是否足够, 原因描述)。
    """
    try:
        import shutil
        usage = shutil.disk_usage(Path(path).anchor)
        free_gb = usage.free / (1024 ** 3)
        if free_gb < min_free_gb:
            return False, f"Low disk space: {free_gb:.1f}GB < {min_free_gb}GB"
        return True, f"{free_gb:.1f}GB free"
    except Exception as e:
        return False, f"Disk check failed: {e}"


def sanitize_iq(iq: np.ndarray) -> tuple[np.ndarray, bool]:
    """清理 IQ 数组中的 NaN/Inf。

    Returns:
        (清理后的数组, 是否检测到异常值)。
    """
    orig = np.asarray(iq)
    nan_mask = np.isnan(orig)
    inf_mask = np.isinf(orig)
    bad = nan_mask | inf_mask

    if not np.any(bad):
        return orig, False

    cleaned = orig.copy()
    cleaned[bad] = 0.0 + 0j
    return cleaned, True


def validate_parameters(
    sample_rate_hz: float,
    center_freq_hz: float,
    bandwidth_hz: float,
    gain_db: float,
    max_gain_db: Optional[float] = None,
) -> list[str]:
    """校验 RF 参数合法性。

    Returns:
        问题列表，空列表 = 全部合法。
    """
    issues = []
    if sample_rate_hz <= 0:
        issues.append(f"Invalid sample_rate: {sample_rate_hz} Hz")
    if center_freq_hz <= 0:
        issues.append(f"Invalid center_freq: {center_freq_hz} Hz")
    if bandwidth_hz <= 0 or bandwidth_hz > sample_rate_hz:
        issues.append(f"Invalid bandwidth: {bandwidth_hz} Hz (sample_rate={sample_rate_hz})")
    if max_gain_db is not None and gain_db > max_gain_db:
        issues.append(f"Gain {gain_db}dB exceeds max {max_gain_db}dB")
    return issues


def recovery_context(
    operation_name: str = "unknown",
    log_fn: Optional[Callable] = None,
) -> dict:
    """生成恢复上下文，用于包裹关键操作。

    用法:
        ctx = recovery_context("sdr_read")
        try:
            data = sdr.receive(1024)
            ctx["success"] = True
        except Exception as e:
            ctx["error"] = str(e)
            data = np.zeros(1024, dtype=np.complex64)
    """
    return {
        "operation": operation_name,
        "timestamp": time.time(),
        "success": False,
        "error": None,
        "fallback_used": False,
    }
