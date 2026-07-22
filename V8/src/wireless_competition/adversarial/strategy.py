"""对抗策略控制器。

根据信道环境和对手活动，动态调整对抗参数。

策略层级：
  L0 — 纯防御：只用 DSSS 处理增益（默认）
  L1 — 频谱占据：最大带宽 + 最大占空比
  L2 — 动态码长：检测到强干扰时增加码长（牺牲速率换可靠性）
  L3 — 跳码：快速切换扩频码（需收发同步）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

import numpy as np


class StrategyLevel(str, Enum):
    """对抗策略等级。"""
    DEFENSIVE = "defensive"       # L0: 纯 DSSS 防御
    SPECTRUM_FILL = "spectrum_fill"  # L1: 频谱占据
    ADAPTIVE_LENGTH = "adaptive_length"  # L2: 动态码长
    CODE_HOPPING = "code_hopping"  # L3: 跳码（高级）


@dataclass
class AdversarialStrategy:
    """一次对抗策略选择。"""
    level: StrategyLevel = StrategyLevel.DEFENSIVE
    code_length: int = 1023
    duty_cycle: float = 1.0          # 占空比 (0-1)，1=连续发射
    bandwidth_fraction: float = 1.0  # 使用带宽比例 (0-1)
    scramble_enabled: bool = True
    randomization_enabled: bool = True
    reason: str = ""


class AdversarialController:
    """对抗策略控制器。

    根据感知输入选择最优对抗参数。
    """

    def __init__(
        self,
        team_id: int = 0,
        max_code_length: int = 4095,
        min_code_length: int = 63,
        max_duty_cycle: float = 1.0,
        seed: Optional[int] = None,
    ):
        self.team_id = team_id
        self.max_code_length = max_code_length
        self.min_code_length = min_code_length
        self.max_duty_cycle = max_duty_cycle
        self._rng = np.random.default_rng(seed if seed is not None else team_id)

        self._current_strategy = AdversarialStrategy()
        self._strategy_history: list[AdversarialStrategy] = []
        self._switch_count: int = 0
        self._min_hold_seconds: float = 0.5  # 最小策略保持时间

    def select_strategy(
        self,
        snr_estimate_db: float = 20.0,
        interference_detected: bool = False,
        rival_count: int = 0,
        goodput_bps: float = 0.0,
        target_goodput_bps: float = 1000.0,
    ) -> AdversarialStrategy:
        """根据当前信道条件选择对抗策略。

        Args:
            snr_estimate_db: 估计信噪比。
            interference_detected: 是否检测到干扰。
            rival_count: 检测到的对手队伍数。
            goodput_bps: 当前有效吞吐率。
            target_goodput_bps: 目标吞吐率。

        Returns:
            选定的对抗策略。
        """
        # L0 默认
        level = StrategyLevel.DEFENSIVE
        code_len = self.min_code_length
        duty = 1.0
        bandwidth = 1.0
        reason = "默认 DSSS 防御模式"

        if snr_estimate_db < 5.0 or interference_detected:
            # 信道差：加大码长，牺牲速率保可靠性
            level = StrategyLevel.ADAPTIVE_LENGTH
            code_len = min(self.max_code_length, self._current_strategy.code_length * 2)
            duty = 1.0
            bandwidth = 1.0
            reason = f"低 SNR ({snr_estimate_db:.1f}dB)，增加码长至 {code_len}"

        elif rival_count > 0 and goodput_bps < target_goodput_bps * 0.5:
            # 有对手且吞吐率低：最大占空比 + 最大带宽
            level = StrategyLevel.SPECTRUM_FILL
            code_len = self._current_strategy.code_length
            duty = self.max_duty_cycle
            bandwidth = 1.0
            reason = f"检测到 {rival_count} 个对手，启动频谱占据"

        elif snr_estimate_db > 15.0 and not interference_detected:
            # 信道好：减小码长，提速
            level = StrategyLevel.DEFENSIVE
            code_len = max(self.min_code_length, self._current_strategy.code_length // 2)
            duty = 1.0
            bandwidth = 1.0
            reason = f"高 SNR ({snr_estimate_db:.1f}dB)，减小码长至 {code_len} 提速"

        else:
            code_len = self._current_strategy.code_length or self.min_code_length

        strategy = AdversarialStrategy(
            level=level,
            code_length=code_len,
            duty_cycle=duty,
            bandwidth_fraction=bandwidth,
            scramble_enabled=True,
            randomization_enabled=True,
            reason=reason,
        )

        self._current_strategy = strategy
        self._strategy_history.append(strategy)
        if len(self._strategy_history) > 1:
            self._switch_count += 1

        return strategy

    @property
    def current_strategy(self) -> AdversarialStrategy:
        return self._current_strategy

    @property
    def total_switches(self) -> int:
        return self._switch_count

    def summary(self) -> dict:
        """策略执行摘要。"""
        return {
            "team_id": self.team_id,
            "total_switches": self._switch_count,
            "current_level": self._current_strategy.level.value,
            "current_code_length": self._current_strategy.code_length,
            "history": [
                {"level": s.level.value, "code_length": s.code_length, "reason": s.reason}
                for s in self._strategy_history[-10:]  # 最近 10 条
            ],
        }
