"""Gold 码标准化生成器。

使用标准优选对多项式 + 循环移位生成真 Gold 序列。
不同队伍的码具有保证的三值互相关特性。
"""

from __future__ import annotations

import numpy as np


# 标准优选对多项式（deg=10, 两个 m 序列 taps）
# 参考文献：Dixon, "Spread Spectrum Systems with Commercial Applications"
# taps1 = [10, 3]  → x^10 + x^3 + 1
# taps2 = [10, 8, 3, 2] → x^10 + x^8 + x^3 + x^2 + 1
# 这两个多项式构成优选对

_TAPS1 = [10, 3]       # m-seq 1
_TAPS2 = [10, 8, 3, 2] # m-seq 2 (优选对)


def _lfsr_step(reg: int, taps: list[int], mask: int) -> tuple[int, int]:
    """单步 LFSR（Fibonacci 结构）。返回 (新寄存器值, 输出比特)。"""
    # Fibonacci: feedback = XOR of tapped bits, shift right, feedback into MSB
    feedback = 0
    for t in taps:
        feedback ^= (reg >> (t - 1)) & 1
    output = reg & 1
    reg = (reg >> 1) | (feedback << (mask.bit_length() - 1))
    return reg & mask, output


def generate_standard_gold_code(
    length: int = 1023,
    shift: int = 0,
) -> np.ndarray:
    """生成标准 Gold 序列（±1）。

    使用 10 阶优选对多项式。不同 shift 值产生不同 Gold 码。
    所有 shift 产生的码具有保证的三值互相关特性 {-1, -t(n), t(n)-2}。

    Args:
        length: 码长（2^10 - 1 = 1023）。
        shift: 循环移位量（0 ~ length-1）。不同队伍用不同 shift。

    Returns:
        int8 ±1 数组。
    """
    mask = (1 << 10) - 1  # 0x3FF

    # 初始化（非零且含高位置位以防止退化）
    reg1 = 0x3FF  # 全1
    reg2 = 0x155  # 交替1

    # 生成 m-seq1（完整周期，前 length 位无 shift）
    mseq1 = np.zeros(length, dtype=np.int8)
    for i in range(length):
        reg1, bit = _lfsr_step(reg1, _TAPS1, mask)
        mseq1[i] = 1 if bit == 0 else -1

    # 生成 m-seq2（完整周期）
    mseq2 = np.zeros(length, dtype=np.int8)
    for i in range(length):
        reg2, bit = _lfsr_step(reg2, _TAPS2, mask)
        mseq2[i] = 1 if bit == 0 else -1

    # 对 m-seq2 做循环移位
    shift = shift % length
    if shift > 0:
        mseq2_shifted = np.concatenate([mseq2[shift:], mseq2[:shift]])
    else:
        mseq2_shifted = mseq2

    # Gold = mseq1 XOR mseq2_shifted，映射到 ±1
    gold = mseq1 * mseq2_shifted  # 1*1=1, 1*(-1)=-1, (-1)*1=-1, (-1)*(-1)=1
    return gold.astype(np.int8)


def generate_team_code(
    length: int = 1023,
    team_id: int = 0,
) -> np.ndarray:
    """为指定队伍生成 Gold 扩频码。

    不同 team_id 使用不同的循环移位，保证互相关特性。

    Args:
        length: 码长（默认 1023）。
        team_id: 队伍编号。

    Returns:
        int8 ±1 数组。
    """
    # 均匀分布移位量，确保不同队伍码互相关最优
    shift = (team_id * (length // 8)) % length
    return generate_standard_gold_code(length, shift)


def verify_cross_correlation(codes: dict[int, np.ndarray]) -> dict:
    """验证多码互相关特性。

    Returns:
        {"max_cc": float, "mean_cc": float, "pairs": [(i,j,cc)]}
    """
    results = {"max_cc": 0.0, "mean_cc": 0.0, "pairs": []}
    team_ids = sorted(codes.keys())
    all_cc = []

    for i, ti in enumerate(team_ids):
        for tj in team_ids[i + 1:]:
            cc = np.abs(np.dot(codes[ti], codes[tj])) / len(codes[ti])
            all_cc.append(cc)
            results["pairs"].append((ti, tj, float(cc)))

    results["max_cc"] = float(np.max(all_cc)) if all_cc else 0.0
    results["mean_cc"] = float(np.mean(all_cc)) if all_cc else 0.0

    return results


# ── 理论互相关边界 ──────────────────────────────────────────

def gold_cross_correlation_bound(n: int = 10) -> float:
    """计算 n 阶 Gold 码互相关理论上界。

    对于 n 阶码（长度 2^n - 1）：
    - n 为奇数时：上界 = 2^{(n+1)/2} + 1
    - n 为偶数且 n≡2(mod 4)：上界 = 2^{(n+2)/2} + 1

    Args:
        n: 阶数（默认 10，码长 1023）。

    Returns:
        归一化互相关上界（除以码长）。
    """
    L = 2 ** n - 1
    if n % 2 == 1:
        bound = 2 ** ((n + 1) // 2) + 1
    else:
        bound = 2 ** ((n + 2) // 2) + 1
    return bound / L
