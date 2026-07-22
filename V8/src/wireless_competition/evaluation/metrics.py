"""评估指标模块。

Goodput、BER、PER 等核心指标的统一定义和计算。
"""

from __future__ import annotations

import numpy as np


def calculate_ber(
    tx_bits: np.ndarray,
    rx_bits: np.ndarray,
) -> float:
    """计算比特错误率 (BER)。

    Args:
        tx_bits: 发送比特 (0/1)。
        rx_bits: 接收比特 (0/1)。

    Returns:
        BER (0–1)。
    """
    tx = np.asarray(tx_bits, dtype=np.uint8).flatten()
    rx = np.asarray(rx_bits, dtype=np.uint8).flatten()
    n = min(len(tx), len(rx))
    if n == 0:
        return 0.0
    errors = int(np.sum(tx[:n] != rx[:n]))
    return errors / n


def calculate_per(
    total_frames: int,
    failed_frames: int,
) -> float:
    """计算包/帧错误率 (PER)。"""
    if total_frames == 0:
        return 0.0
    return failed_frames / total_frames


def calculate_goodput_bps(
    correct_payload_bytes: int,
    elapsed_time_s: float,
) -> float:
    """计算有效吞吐率 (Goodput, bits/s)。

    Args:
        correct_payload_bytes: 通过 CRC 校验的有效载荷字节总数。
        elapsed_time_s: 经过时间（秒）。

    Returns:
        Goodput (bits/s)。
    """
    if elapsed_time_s <= 0:
        return 0.0
    return (correct_payload_bytes * 8) / elapsed_time_s


def calculate_throughput_bps(
    total_bytes: int,
    elapsed_time_s: float,
) -> float:
    """计算原始吞吐率（含所有开销）。

    Args:
        total_bytes: 总传输字节（含包头、CRC、FEC 等）。
        elapsed_time_s: 经过时间。

    Returns:
        吞吐率 (bits/s)。
    """
    if elapsed_time_s <= 0:
        return 0.0
    return (total_bytes * 8) / elapsed_time_s


def summarize_metrics(
    ber_list: list[float],
    per_list: list[float],
    goodput_list: list[float],
) -> dict:
    """汇总多次运行的指标统计。

    Returns:
        含 mean, std, median, p5, p95 的字典。
    """
    def stats(arr):
        a = np.array(arr)
        if len(a) == 0:
            return {"mean": float("nan"), "std": float("nan"),
                    "median": float("nan"), "p5": float("nan"), "p95": float("nan")}
        return {
            "mean": float(np.mean(a)),
            "std": float(np.std(a)),
            "median": float(np.median(a)),
            "p5": float(np.percentile(a, 5)),
            "p95": float(np.percentile(a, 95)),
        }

    return {
        "ber": stats(ber_list),
        "per": stats(per_list),
        "goodput_bps": stats(goodput_list),
    }
