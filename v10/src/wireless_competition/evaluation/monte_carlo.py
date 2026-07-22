"""Monte Carlo 测试框架。

支持多种子重复仿真，统一报告平均/低分位/最坏指标。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional

import numpy as np

from ..common.seeds import create_seed_sequence
from ..common.types import ChannelConfig, DecodeResult, FECType, ModulationType, ProfileID
from ..evaluation.metrics import (
    calculate_goodput_bps,
    calculate_per,
    summarize_metrics,
)


def run_monte_carlo(
    run_func,
    n_seeds: int = 20,
    base_seed: int = 42,
    **run_kwargs,
) -> dict[str, Any]:
    """运行 Monte Carlo 仿真。

    Args:
        run_func: 单次运行函数，签名为 func(seed, **kwargs) -> dict。
        n_seeds: 种子数量。
        base_seed: 基础种子。
        **run_kwargs: 传递给 run_func 的额外参数。

    Returns:
        汇总统计字典。
    """
    seeds = create_seed_sequence(n_seeds, base_seed)

    ber_list = []
    per_list = []
    goodput_list = []
    failure_list = []
    all_metrics = []

    for i, seed in enumerate(seeds):
        try:
            result = run_func(seed=seed, **run_kwargs)
            all_metrics.append(result)
            ber_list.append(result.get("ber", float("nan")))
            per_list.append(result.get("per", float("nan")))
            goodput_list.append(result.get("goodput_bps", 0.0))
            failure_list.append(0)
        except Exception as e:
            all_metrics.append({"error": str(e), "seed": seed})
            ber_list.append(float("nan"))
            per_list.append(1.0)
            goodput_list.append(0.0)
            failure_list.append(1)

    summary = summarize_metrics(ber_list, per_list, goodput_list)
    summary["n_seeds"] = n_seeds
    summary["total_failures"] = int(sum(failure_list))
    summary["failure_rate"] = float(np.mean(failure_list))
    summary["base_seed"] = base_seed

    return summary
