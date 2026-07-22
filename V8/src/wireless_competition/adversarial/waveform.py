"""对抗性波形设计。

在 DSSS 基础上叠加以下对抗特性：
1. 不规则帧结构（随机化前导位置和同步字，让对手检测器更难锁定）
2. 最大带宽利用（在规则允许范围内占满频谱）
3. 功率谱平坦化（让信号看起来像白噪声）
4. 可变码长（动态调整扩频因子，适应不同信道条件）
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from .dsss import SpreadingCodeManager, spread, despread


class AdversarialWaveform:
    """对抗性波形设计器。

    特性：
      - DSSS 扩频（天然抗干扰 + 对对手呈现噪声特性）
      - 随机化帧参数（让对手难以锁定）
      - 功率谱平坦化（类噪声特性最大化）
    """

    def __init__(
        self,
        team_id: int = 0,
        code_length: int = 1023,
        chip_rate_factor: int = 1,
        enable_randomization: bool = True,
        seed: Optional[int] = None,
    ):
        """
        Args:
            team_id: 队伍编号（决定扩频码）。
            code_length: 扩频码长度（越大处理增益越高，但速率越低）。
            chip_rate_factor: 码片速率倍数（1=码片速率=比特速率×码长）。
            enable_randomization: 是否启用随机化对抗特性。
            seed: 随机种子。
        """
        self.team_id = team_id
        self.code_length = code_length
        self.chip_rate_factor = chip_rate_factor
        self.enable_randomization = enable_randomization

        self._rng = np.random.default_rng(seed if seed is not None else team_id)
        self._code_manager = SpreadingCodeManager(team_id, code_length)
        self._code = self._code_manager.our_code

    # ── 发射端 ──────────────────────────────────────────────

    def modulate(
        self,
        bits: np.ndarray,
        scramble: bool = True,
    ) -> np.ndarray:
        """将比特调制成对抗性码片序列。

        流程：比特 → (可选) 随机化 → DSSS 扩频 → 功率归一化

        Args:
            bits: 输入比特 (0/1)。
            scramble: 是否对发射比特做随机化（让频谱更平坦）。

        Returns:
            码片序列 (±1)。
        """
        bits_arr = np.asarray(bits, dtype=np.uint8).flatten()

        if scramble and self.enable_randomization:
            bits_arr = self._scramble_bits(bits_arr)

        chips = spread(bits_arr, self._code)
        return chips

    def _scramble_bits(self, bits: np.ndarray) -> np.ndarray:
        """比特随机化：用固定种子 XOR 打散连续 0/1。

        好处：避免长串 0 或 1 导致的直流分量，频谱更平坦。
        """
        scrambler = np.random.default_rng(self.team_id * 7 + 13)
        mask = (scrambler.random(len(bits)) > 0.5).astype(np.uint8)
        return bits ^ mask

    # ── 接收端 ──────────────────────────────────────────────

    def demodulate(
        self,
        chips: np.ndarray,
        descramble: bool = True,
    ) -> np.ndarray:
        """从码片序列恢复比特。

        Args:
            chips: 接收码片序列。
            descramble: 是否解扰。

        Returns:
            恢复的比特 (0/1)。
        """
        bits = despread(chips, self._code, output_bits=True)

        if descramble and self.enable_randomization:
            bits = self._scramble_bits(bits)  # XOR 两次还原

        return bits

    def soft_demodulate(self, chips: np.ndarray) -> np.ndarray:
        """软解调：返回相关值而非硬判决。

        Returns:
            软值数组（正值 = 倾向 bit 0，负值 = 倾向 bit 1）。
        """
        return despread(chips, self._code, output_bits=False)

    # ── 干扰仿真 ──────────────────────────────────────────

    def simulate_rival_signal(
        self,
        rival_team_id: int,
        n_bits: int = 100,
    ) -> np.ndarray:
        """生成模拟对手信号（用对手码扩频随机比特）。

        Args:
            rival_team_id: 对手队伍编号。
            n_bits: 模拟比特数。

        Returns:
            对手码片序列。
        """
        rival_code = self._code_manager.get_rival_code(rival_team_id)
        rival_bits = self._rng.integers(0, 2, n_bits).astype(np.uint8)
        return spread(rival_bits, rival_code)

    # ── 分析工具 ──────────────────────────────────────────

    def processing_gain_db(self) -> float:
        """当前配置的处理增益。"""
        return 10.0 * np.log10(self.code_length)

    def effective_data_rate(self, symbol_rate: float) -> float:
        """计算有效数据率。

        Args:
            symbol_rate: 码片速率 (chips/s)。

        Returns:
            有效数据率 (bits/s)。
        """
        return symbol_rate / self.code_length

    def code_properties(self) -> dict:
        """返回当前波形属性。"""
        rival_codes = {
            i: self._code_manager.get_rival_code(i)
            for i in range(1, 4)
        }
        cross_corrs = {}
        for rid, rc in rival_codes.items():
            # 归一化互相关
            cc = np.abs(np.dot(self._code, rc)) / self.code_length
            cross_corrs[f"team_{rid}"] = float(cc)

        return {
            "team_id": self.team_id,
            "code_length": self.code_length,
            "processing_gain_db": self.processing_gain_db(),
            "chip_rate_multiplier": self.chip_rate_factor,
            "randomization_enabled": self.enable_randomization,
            "cross_correlation_with_rivals": cross_corrs,
        }


# ── 帧随机化器 ───────────────────────────────────────────────

class FrameRandomizer:
    """随机化帧结构参数，增加对手检测难度。

    在合法帧结构基础上，随机化以下参数：
      - 前导长度（在一定范围内变化）
      - 保护间隔长度
      - 同步字位置（在帧内偏移）
      - 导频密度

    己方接收端共享随机种子，可以正确解帧。
    """

    def __init__(self, seed: int = 42):
        self._rng = np.random.default_rng(seed)

    def randomize_preamble_length(
        self,
        base: int = 64,
        variation: int = 16,
    ) -> int:
        """随机化前导长度。"""
        return base + self._rng.integers(-variation, variation + 1)

    def randomize_guard_length(
        self,
        base: int = 16,
        variation: int = 8,
    ) -> int:
        """随机化保护间隔。"""
        return max(4, base + self._rng.integers(-variation, variation + 1))

    def randomize_sync_offset(
        self,
        max_offset: int = 8,
    ) -> int:
        """随机化同步字偏移。"""
        return self._rng.integers(0, max_offset + 1)

    def randomize_pilot_density(
        self,
        base_every_n_symbols: int = 16,
        variation: int = 4,
    ) -> int:
        """随机化导频密度。"""
        return max(4, base_every_n_symbols + self._rng.integers(-variation, variation + 1))
