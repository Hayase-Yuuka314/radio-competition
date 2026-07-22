"""直接序列扩频 (DSSS) 引擎。

核心原理：
  发送端：1 bit → 乘以 N 位伪随机码 → N 个码片（宽带信号）
  接收端：N 码片 × 相同伪随机码 → 累加 → 恢复 1 bit（处理增益 10*log10(N) dB）

码生成：
  使用标准 Gold 码（优选对多项式 + 循环移位），保证三值互相关特性。
  见 gold_code.py 获取码的理论验证和互相关分析。

优势：
  - 己方获得处理增益（如 N=1023 → ~30dB），抗干扰能力极强
  - 对手看到的是宽带低功率噪声，难以检测/解调
  - 纯软件实现，CPU 友好（相关运算可用 FFT 加速）
  - 不"故意发射干扰"——你只是在正常通信，信号本身天然对抗
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from .gold_code import (
    generate_gold_code_any_length,
    generate_team_code,
    map_seed_to_shift,
    verify_cross_correlation,
)


# ── 伪随机码生成 ──────────────────────────────────────────────

def generate_gold_code(
    length: int = 1023,
    seed: int = 42,
) -> np.ndarray:
    """生成标准 Gold 序列（±1）。

    使用 10 阶优选对多项式 + 循环移位生成真 Gold 码。
    seed 被映射为循环移位量，不同 seed → 不同移位 → 不同的正交 Gold 码。
    所有码具有保证的三值互相关特性。

    Args:
        length: 码长。任意值，内部基于 n=10 (1023位) 基截取/平铺。
        seed: 种子，被映射为循环移位量以产生不同的 Gold 码。

    Returns:
        int8 数组，+1 或 -1。
    """
    shift = map_seed_to_shift(seed, length)
    return generate_gold_code_any_length(length, shift)


def generate_spreading_code(
    length: int = 1023,
    team_id: int = 0,
) -> np.ndarray:
    """为指定队伍生成唯一的 Gold 扩频码。

    不同 team_id 产生不同的 Gold 码，具有保证的三值互相关特性。
    队伍间扩频码相互正交，CDMA 多址接入。

    Args:
        length: 码长。
        team_id: 队伍编号（0-N）。

    Returns:
        int8 ±1 扩频码。
    """
    return generate_team_code(length, team_id)


# ── 扩频 / 解扩 ─────────────────────────────────────────────

def spread(
    bits: np.ndarray,
    code: np.ndarray,
) -> np.ndarray:
    """扩频：每个比特乘以整个码序列。

    Args:
        bits: 输入比特 (0/1 或 ±1)。
        code: 扩频码 (±1)。

    Returns:
        码片序列 (±1)，长度 = len(bits) * len(code)。
    """
    bits_arr = np.asarray(bits, dtype=np.float64).flatten()

    # 检测输入格式：含 0 → 0/1格式，否则 → ±1格式
    is_binary_01 = 0.0 in set(np.unique(bits_arr))

    if is_binary_01:
        bits_arr = 1.0 - 2.0 * bits_arr  # 0→+1, 1→-1
    # else: 已经是 ±1，直接使用

    code_arr = np.asarray(code, dtype=np.float64).flatten()
    n_code = len(code_arr)

    # 外积 + 展平
    chips = np.outer(bits_arr, code_arr).ravel()
    return chips.astype(np.float64)


def despread(
    chips: np.ndarray,
    code: np.ndarray,
    output_bits: bool = True,
) -> np.ndarray:
    """解扩：每 N 个码片与码做内积，恢复 1 比特。

    Args:
        chips: 接收码片序列。
        code: 扩频码 (±1)。
        output_bits: True 返回 0/1 比特，False 返回软值。

    Returns:
        恢复的比特或软值数组。
    """
    code_arr = np.asarray(code, dtype=np.float64).flatten()
    n_code = len(code_arr)
    n_chips = len(chips)

    # 截断到完整码长倍数
    n_bits = n_chips // n_code
    if n_bits == 0:
        return np.array([], dtype=np.uint8 if output_bits else np.float64)

    chips_trimmed = chips[:n_bits * n_code]
    chips_2d = chips_trimmed.reshape(n_bits, n_code)

    # 内积：每行与 code 点乘然后求和
    soft_values = np.dot(chips_2d, code_arr)  # shape (n_bits,)

    if output_bits:
        return (soft_values <= 0).astype(np.uint8)
    else:
        return soft_values


def processing_gain_db(code_length: int) -> float:
    """计算 DSSS 处理增益。

    PG(dB) = 10 * log10(码长)

    码长 1023 → ~30.1 dB
    码长 255  → ~24.1 dB
    码长 63   → ~18.0 dB
    """
    return 10.0 * np.log10(code_length)


# ── 快速相关解扩（FFT 加速，适合长码）─────────────────────────

def despread_fft(
    chips: np.ndarray,
    code: np.ndarray,
    output_bits: bool = True,
) -> np.ndarray:
    """用 FFT 快速相关解扩（适合码长 > 1023 时加速）。

    原理：循环相关 = IFFT(FFT(chips) * conj(FFT(code)))
    """
    code_arr = np.asarray(code, dtype=np.float64)
    n_code = len(code_arr)

    # 零填充到 2 的幂
    n_fft = 1
    while n_fft < len(chips) + n_code:
        n_fft *= 2

    chip_fft = np.fft.rfft(chips, n=n_fft)
    code_fft = np.fft.rfft(np.flip(code_arr), n=n_fft)
    corr = np.fft.irfft(chip_fft * code_fft, n=n_fft)

    # 取码对齐点的相关值
    n_bits = (len(chips) - n_code) // n_code + 1
    result = np.zeros(n_bits, dtype=np.float64)
    for i in range(n_bits):
        idx = i * n_code + n_code - 1
        if idx < len(corr):
            result[i] = corr[idx]
        else:
            result[i] = 0.0

    if output_bits:
        return (result <= 0).astype(np.uint8)  # ≤0 → bit 1 (因为 code 是 ±1)
    else:
        return result


# ── 多码管理 ────────────────────────────────────────────────

class SpreadingCodeManager:
    """扩频码管理器。

    管理多个队伍的扩频码，支持码切换和自动选择。
    """

    def __init__(self, our_team_id: int = 0, code_length: int = 1023):
        self.our_team_id = our_team_id
        self.code_length = code_length
        self._codes: dict[int, np.ndarray] = {}

        # 己方码
        self.our_code = self._get_or_create(our_team_id)

    def _get_or_create(self, team_id: int) -> np.ndarray:
        if team_id not in self._codes:
            self._codes[team_id] = generate_spreading_code(
                self.code_length, team_id
            )
        return self._codes[team_id]

    def get_rival_code(self, team_id: int) -> np.ndarray:
        """获取对手码（用于仿真对手信号）。"""
        return self._get_or_create(team_id)

    @property
    def processing_gain(self) -> float:
        return processing_gain_db(self.code_length)
