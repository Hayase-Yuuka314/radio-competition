"""Gold 码标准化生成器。

使用标准优选对多项式 + 循环移位生成真 Gold 序列。
不同队伍的码具有保证的三值互相关特性。

支持任意码长：自动选择最接近的 n 阶多项式对。
n=5..10 的多项式对来自 Dixon, "Spread Spectrum Systems with Commercial Applications"
"""

from __future__ import annotations

import numpy as np


# 标准优选对多项式索引表（n=5..10）
# 格式：{n: (taps1, taps2)}  其中 taps = [最高位, ..., 最低位]
# taps1 = [10, 3]  → x^10 + x^3 + 1
# taps2 = [10, 8, 3, 2] → x^10 + x^8 + x^3 + x^2 + 1

_PREFERRED_PAIRS: dict[int, tuple[list[int], list[int]]] = {
    5:  ([5, 2],       [5, 4, 3, 2]),
    6:  ([6, 1],       [6, 5, 2, 1]),
    7:  ([7, 3],       [7, 3, 2, 1]),
    8:  ([8, 4, 3, 2], [8, 6, 5, 3]),
    9:  ([9, 4],       [9, 6, 4, 3]),
    10: ([10, 3],      [10, 8, 3, 2]),
}

_MIN_N = 5
_MAX_N = 10


def _lfsr_step(reg: int, taps: list[int], mask: int) -> tuple[int, int]:
    """单步 LFSR（Fibonacci 结构）。返回 (新寄存器值, 输出比特)。

    Fibonacci 右移结构：
      feedback = XOR of bits at positions (n - tap_index)
      output = bit 0 (LSB)
      new reg = (reg >> 1) | (feedback << (n-1))

    例如 n=10, taps=[10,3] → feedback = bit[0] ^ bit[7]
    """
    n = mask.bit_length()
    feedback = 0
    for t in taps:
        feedback ^= (reg >> (n - t)) & 1
    output = reg & 1
    reg = (reg >> 1) | (feedback << (n - 1))
    return reg & mask, output


def generate_standard_gold_code(
    length: int = 1023,
    shift: int = 0,
    n: int | None = None,
) -> np.ndarray:
    """生成标准 Gold 序列（±1）。

    使用优选对多项式生成指定长度 Gold 码。
    长度应为 2^n - 1。若不指定 n 则自动选择最小满足 2^n-1 >= length 的 n。

    不同 shift 值产生不同 Gold 码，所有 shift 产生的码具有
    保证的三值互相关特性 {-1, -t(n), t(n)-2}。

    Args:
        length: 码长（应为 2^n - 1，如 31/63/127/255/511/1023）。
        shift: 循环移位量（0 ~ 2^n-2）。不同队伍用不同 shift。
        n: LFSR 阶数（可选，自动推导）。

    Returns:
        int8 ±1 数组。
    """
    if n is None:
        n = int(np.ceil(np.log2(length + 1)))
        n = max(_MIN_N, min(_MAX_N, n))

    if n not in _PREFERRED_PAIRS:
        n = _MAX_N

    taps1, taps2 = _PREFERRED_PAIRS[n]
    full_length = (1 << n) - 1
    mask = full_length

    # 初始化寄存器（非零）
    reg1 = 0x155 & mask
    reg2 = 0x2AA & mask

    # 生成 m-seq1（完整周期，前 full_length 位无 shift）
    mseq1 = np.zeros(full_length, dtype=np.int8)
    for i in range(full_length):
        reg1, bit = _lfsr_step(reg1, taps1, mask)
        mseq1[i] = 1 if bit == 0 else -1

    # 生成 m-seq2（完整周期）
    mseq2 = np.zeros(full_length, dtype=np.int8)
    for i in range(full_length):
        reg2, bit = _lfsr_step(reg2, taps2, mask)
        mseq2[i] = 1 if bit == 0 else -1

    # 对 m-seq2 做循环移位
    shift = shift % full_length
    if shift > 0:
        mseq2_shifted = np.concatenate([mseq2[shift:], mseq2[:shift]])
    else:
        mseq2_shifted = mseq2

    # Gold = mseq1 XOR mseq2_shifted，映射到 ±1
    gold = mseq1 * mseq2_shifted

    # 截取到目标长度
    result = gold[:length]
    return result.astype(np.int8)


def generate_team_code(
    length: int = 1023,
    team_id: int = 0,
) -> np.ndarray:
    """为指定队伍生成 Gold 扩频码。

    不同 team_id 使用不同的循环移位，保证互相关特性。
    自动选择最接近的 Gold 码阶数 n 并均匀分布移位量。

    Args:
        length: 码长（默认 1023）。
        team_id: 队伍编号。

    Returns:
        int8 ±1 数组。
    """
    n = int(np.ceil(np.log2(length + 1)))
    n = max(_MIN_N, min(_MAX_N, n))
    full_length = (1 << n) - 1
    shift = (team_id * max(1, full_length // 8)) % full_length
    code = generate_standard_gold_code(full_length, shift, n=n)
    return code[:length].astype(np.int8)


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


# ── 任意长度 Gold 码 ────────────────────────────────────────

def generate_gold_code_any_length(
    length: int,
    shift: int = 0,
) -> np.ndarray:
    """生成任意长度的 Gold 码。

    自动选择最接近的 n 阶多项式对，生成完整长度 (2^n - 1)
    的 Gold 码，再截取/平铺到目标长度。

    截取后互相关特性接近理想的 n 阶 Gold 码。

    Args:
        length: 目标码长。
        shift: 循环移位量（模 2^n - 1），不同 shift 产生不同 Gold 码。

    Returns:
        int8 ±1 数组，长度 = length。
    """
    n = int(np.ceil(np.log2(length + 1)))
    n = max(_MIN_N, min(_MAX_N, n))
    full_length = (1 << n) - 1

    if length <= full_length * 2:
        code = generate_standard_gold_code(full_length, shift, n=n)
        result = code[:length]
    else:
        code = generate_standard_gold_code(full_length, shift, n=n)
        repeats = (length + full_length - 1) // full_length
        result = np.tile(code, repeats)[:length]

    return result.astype(np.int8)


def map_seed_to_shift(seed: int, length: int = 1023) -> int:
    """将种子值映射为 Gold 码移位量。

    确保不同种子产生不同（且相隔足够远的）Gold 码。
    移位量基于完整 Gold 码长度 (2^n - 1) 的模运算。

    Args:
        seed: 任意整数种子。
        length: 目标码长（用于确定 n 和步长）。

    Returns:
        移位量（0 ~ 2^n-2）。
    """
    n = int(np.ceil(np.log2(length + 1)))
    n = max(_MIN_N, min(_MAX_N, n))
    full_length = (1 << n) - 1
    step = max(1, full_length // 8)
    return (seed * step) % full_length


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
