"""随机种子管理。

所有随机过程必须可复现。此模块提供统一的种子设置和 RNG 创建。
"""

from __future__ import annotations

import random
import time
from typing import Optional

import numpy as np


# 全局基础种子（可配置）
_BASE_SEED: int = 42


def set_base_seed(seed: int) -> None:
    """设置全局基础种子。"""
    global _BASE_SEED
    _BASE_SEED = seed


def get_base_seed() -> int:
    """获取当前全局基础种子。"""
    return _BASE_SEED


def create_rng(seed: Optional[int] = None) -> np.random.Generator:
    """创建一个独立的 NumPy 随机数生成器。

    Args:
        seed: 可选显式种子。若为 None，使用全局基础种子。

    Returns:
        np.random.Generator 实例。
    """
    s = seed if seed is not None else _BASE_SEED
    return np.random.default_rng(s)


def create_seed_sequence(n: int, base: Optional[int] = None) -> list[int]:
    """生成 n 个不重复的派生种子。

    用于 Monte Carlo 测试时为每个 scenario 分配独立种子。

    Args:
        n: 需要的种子数量。
        base: 基础种子，默认使用全局基础种子。

    Returns:
        整数种子列表。
    """
    b = base if base is not None else _BASE_SEED
    rng = np.random.SeedSequence(b)
    children = rng.spawn(n)
    return [int(c.generate_state(1)[0]) for c in children]


def set_all_seeds(seed: int) -> None:
    """同时设置 Python random、NumPy 全局状态和本模块基础种子。

    注意：推荐使用 ``create_rng()`` 获取独立 RNG 而不是依赖全局状态。
    """
    set_base_seed(seed)
    random.seed(seed)
    np.random.seed(seed)


def timestamp_seed() -> int:
    """从当前时间生成种子（仅用于需要真正随机性的场合）。"""
    return int(time.time_ns() % (2**31))
