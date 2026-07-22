"""自适应策略联动模块。

将 AdversarialController 接入接收端流水线，
根据解码结果自动调整对抗参数。
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from ..adversarial.strategy import AdversarialController, AdversarialStrategy
from ..common.types import DecodeResult


class AdaptiveRXWrapper:
    """自适应接收端包装器。

    在 SimulationReceiver 基础上增加策略选择层。
    每帧处理后根据 SNR/PER/干扰状态选择最优策略。
    """

    def __init__(
        self,
        team_id: int = 0,
        min_code_length: int = 63,
        max_code_length: int = 1023,
        seed: Optional[int] = None,
    ):
        self._controller = AdversarialController(
            team_id=team_id,
            min_code_length=min_code_length,
            max_code_length=max_code_length,
            seed=seed,
        )
        self._history: list[dict] = []  # 策略切换历史
        self._current_code_length = min_code_length
        # 初始化控制器策略为最小码长
        self._controller._current_strategy.code_length = min_code_length

    def select_strategy(
        self,
        snr_db: float = 20.0,
        per: float = 0.0,
        goodput_bps: float = 1000.0,
        interference_detected: bool = False,
        rival_count: int = 0,
    ) -> AdversarialStrategy:
        """根据当前信道条件选择策略。

        Args:
            snr_db: SNR 估计。
            per: 包错误率。
            goodput_bps: 当前 Goodput。
            interference_detected: ML 是否检测到干扰。
            rival_count: 检测到的对手数。

        Returns:
            AdversarialStrategy。
        """
        strategy = self._controller.select_strategy(
            snr_estimate_db=snr_db,
            interference_detected=interference_detected,
            rival_count=rival_count,
            goodput_bps=goodput_bps,
        )

        if strategy.code_length != self._current_code_length:
            self._history.append({
                "old_code_length": self._current_code_length,
                "new_code_length": strategy.code_length,
                "level": strategy.level.value,
                "reason": strategy.reason,
                "snr_db": snr_db,
                "per": per,
            })
            self._current_code_length = strategy.code_length

        return strategy

    def on_frame_result(
        self,
        result: DecodeResult,
        rival_count: int = 0,
    ) -> AdversarialStrategy:
        """根据单帧解码结果更新策略。

        Args:
            result: 解码结果。
            rival_count: 估计的对手数。

        Returns:
            新策略。
        """
        snr = result.snr_estimate_db if not np.isnan(result.snr_estimate_db) else 20.0
        per = 0.0 if result.payload_crc_pass else 1.0

        # ML 检测到干扰？
        interference = (
            result.model_prediction is not None
            and result.model_prediction not in ("clean", "unknown", "")
            and result.model_confidence > 0.5
        )

        return self.select_strategy(
            snr_db=snr,
            per=per,
            interference_detected=interference,
            rival_count=rival_count,
        )

    @property
    def current_code_length(self) -> int:
        return self._current_code_length

    @property
    def switch_count(self) -> int:
        return self._controller.total_switches

    @property
    def history(self) -> list[dict]:
        return self._history[-20:]  # 最近 20 条

    def summary(self) -> dict:
        """策略摘要。"""
        ctrl_summary = self._controller.summary()
        ctrl_summary["wrapper_switches"] = len(self._history)
        ctrl_summary["current_code_length"] = self._current_code_length
        return ctrl_summary
