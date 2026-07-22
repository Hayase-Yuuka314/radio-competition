"""前向纠错 (FEC) 编码与译码模块。

支持：
- 无编码 (NONE)
- 重复码 (REPETITION)：仅用于调试
- 卷积码 (CONVOLUTIONAL)：速率 1/2, K=7 (NASA-DSN 标准)
"""

from __future__ import annotations

from enum import Enum, auto

import numpy as np

from ..common.types import FECType


class ViterbiDecoder:
    """维特比硬判决/软判决译码器。

    卷积码参数：速率 1/2, K=7, 生成多项式 G1=0o171, G2=0o133。
    """

    # NASA-DSN 标准生成多项式
    G1 = 0o171  # 1111001
    G2 = 0o133  # 1011011
    CONSTRAINT_LENGTH = 7
    NUM_STATES = 1 << (CONSTRAINT_LENGTH - 1)  # 64

    def __init__(self):
        self._trellis = self._build_trellis()

    @staticmethod
    def _build_trellis() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """构建网格图（状态转移表）。

        约束长度 K=7, 64 状态, 生成多项式 G1=0o171, G2=0o133.
        状态 bits: [b5,b4,b3,b2,b1,b0] (b5=MSB, b0=LSB).
        新输入 bit 进入 LSB, b0 移出.

        输出 bit 对 = (g1_out, g2_out) 编码为 2-bit integer: (g1<<1)|g2.

        Returns:
            (next_state0, next_state1, output0, output1)
            每个形状为 (64,) 的数组。
        """
        n = 64
        ns0 = np.zeros(n, dtype=np.int32)
        ns1 = np.zeros(n, dtype=np.int32)
        out0 = np.zeros(n, dtype=np.int32)
        out1 = np.zeros(n, dtype=np.int32)

        for state in range(n):
            b5 = (state >> 5) & 1
            b4 = (state >> 4) & 1
            b3 = (state >> 3) & 1
            b2 = (state >> 2) & 1
            b1 = (state >> 1) & 1
            b0 = state & 1

            # 输入 0: g1 = 0 ^ b5 ^ b4 ^ b3 ^ b0, g2 = 0 ^ b4 ^ b3 ^ b1 ^ b0
            g1_0 = 0 ^ b5 ^ b4 ^ b3 ^ b0
            g2_0 = 0 ^ b4 ^ b3 ^ b1 ^ b0
            next0 = ((state << 1) | 0) & 0x3F
            ns0[state] = next0
            out0[state] = (g1_0 << 1) | g2_0

            # 输入 1: g1 = 1 ^ b5 ^ b4 ^ b3 ^ b0, g2 = 1 ^ b4 ^ b3 ^ b1 ^ b0
            g1_1 = 1 ^ b5 ^ b4 ^ b3 ^ b0
            g2_1 = 1 ^ b4 ^ b3 ^ b1 ^ b0
            next1 = ((state << 1) | 1) & 0x3F
            ns1[state] = next1
            out1[state] = (g1_1 << 1) | g2_1

        return ns0, ns1, out0, out1

    def decode_hard(self, received: np.ndarray) -> np.ndarray:
        """硬判决维特比译码。

        Args:
            received: 接收比特数组 (0/1)，长度必须为偶数。

        Returns:
            译码后比特数组。
        """
        received = np.asarray(received, dtype=np.int32).flatten()
        if len(received) % 2 != 0:
            raise ValueError(f"Input length must be even, got {len(received)}")

        n_steps = len(received) // 2
        ns0, ns1, out0, out1 = self._trellis

        # 路径度量
        pm = np.full(64, 1e12, dtype=np.float64)
        pm[0] = 0.0
        paths = np.zeros((n_steps + 1, 64), dtype=np.int32)

        for step in range(n_steps):
            rx_bits = received[step * 2 : step * 2 + 2]
            rx_val = (rx_bits[0] << 1) | rx_bits[1]

            new_pm = np.full(64, 1e12, dtype=np.float64)
            new_paths = np.zeros(64, dtype=np.int32)

            for state in range(64):
                if pm[state] > 1e11:
                    continue

                # 分支 0
                hamming0 = bin(out0[state] ^ rx_val).count('1')
                cand = pm[state] + hamming0
                if cand < new_pm[ns0[state]]:
                    new_pm[ns0[state]] = cand
                    new_paths[ns0[state]] = (state << 1) | 0

                # 分支 1
                hamming1 = bin(out1[state] ^ rx_val).count('1')
                cand = pm[state] + hamming1
                if cand < new_pm[ns1[state]]:
                    new_pm[ns1[state]] = cand
                    new_paths[ns1[state]] = (state << 1) | 1

            pm = new_pm
            paths[step + 1] = new_paths

        # 回溯
        best_state = int(np.argmin(pm))
        decoded = np.zeros(n_steps, dtype=np.uint8)
        for step in range(n_steps, 0, -1):
            prev = paths[step, best_state]
            decoded[step - 1] = prev & 1
            best_state = prev >> 1

        return decoded

    def decode_soft(self, llr: np.ndarray) -> np.ndarray:
        """软判决维特比译码（LLR 输入）。

        使用标准分支度量：对每个输出比特 b（期望值），
        分支代价 = -0.5 * (1-2b) * LLR
          b=0 → -0.5*LLR (LLR>0 表示匹配，代价小)
          b=1 → +0.5*LLR

        Args:
            llr: LLR 数组，长度必须为偶数。
                 正值=更可能是0，负值=更可能是1。

        Returns:
            译码后比特数组。
        """
        llr = np.asarray(llr, dtype=np.float64).flatten()
        if len(llr) % 2 != 0:
            raise ValueError(f"Input length must be even, got {len(llr)}")

        n_steps = len(llr) // 2
        ns0, ns1, out0, out1 = self._trellis

        # 预计算每个输出比特对的期望比特值
        exp_b0_1 = np.array([(out0[s] >> 1) & 1 for s in range(64)], dtype=np.int32)
        exp_b0_2 = np.array([out0[s] & 1 for s in range(64)], dtype=np.int32)
        exp_b1_1 = np.array([(out1[s] >> 1) & 1 for s in range(64)], dtype=np.int32)
        exp_b1_2 = np.array([out1[s] & 1 for s in range(64)], dtype=np.int32)

        # 预计算分支度量偏移：对每个状态和每个输出位 (0或1)
        # branch_metric = Σ -0.5*(1-2*expected_bit)*LLR_bit
        pm = np.full(64, np.inf, dtype=np.float64)
        pm[0] = 0.0
        paths = np.zeros((n_steps + 1, 64), dtype=np.int32)

        for step in range(n_steps):
            l0 = llr[step * 2]
            l1 = llr[step * 2 + 1]

            new_pm = np.full(64, np.inf, dtype=np.float64)
            new_paths = np.zeros(64, dtype=np.int32)

            for state in range(64):
                if pm[state] == np.inf:
                    continue

                # 分支 0 的代价
                cost_0_1 = -0.5 * (1 - 2 * exp_b0_1[state]) * l0
                cost_0_2 = -0.5 * (1 - 2 * exp_b0_2[state]) * l1
                cand0 = pm[state] + cost_0_1 + cost_0_2
                if cand0 < new_pm[ns0[state]]:
                    new_pm[ns0[state]] = cand0
                    new_paths[ns0[state]] = (state << 1) | 0

                # 分支 1 的代价
                cost_1_1 = -0.5 * (1 - 2 * exp_b1_1[state]) * l0
                cost_1_2 = -0.5 * (1 - 2 * exp_b1_2[state]) * l1
                cand1 = pm[state] + cost_1_1 + cost_1_2
                if cand1 < new_pm[ns1[state]]:
                    new_pm[ns1[state]] = cand1
                    new_paths[ns1[state]] = (state << 1) | 1

            pm = new_pm
            paths[step + 1] = new_paths

        # 回溯
        best_state = int(np.argmin(pm))
        decoded = np.zeros(n_steps, dtype=np.uint8)
        for step in range(n_steps, 0, -1):
            prev = paths[step, best_state]
            decoded[step - 1] = prev & 1
            best_state = prev >> 1

        return decoded


# 全局译码器实例（可复用）
_viterbi_decoder: ViterbiDecoder | None = None


def get_viterbi_decoder() -> ViterbiDecoder:
    """获取共享维特比译码器实例。"""
    global _viterbi_decoder
    if _viterbi_decoder is None:
        _viterbi_decoder = ViterbiDecoder()
    return _viterbi_decoder


def convolutional_encode(bits: np.ndarray) -> np.ndarray:
    """卷积编码（速率 1/2, K=7, G1=0o171, G2=0o133）。

    标准 NASA-DSN 卷积编码器：
    - 6-bit 状态寄存器 [b5,b4,b3,b2,b1,b0]
    - 输出：g1 = input ^ b5 ^ b4 ^ b3 ^ b0
           g2 = input ^ b4 ^ b3 ^ b1 ^ b0
    - 状态更新：state = ((state << 1) | input) & 0x3F

    Args:
        bits: 输入比特数组 (0/1)。

    Returns:
        编码后比特数组（长度×2）。
    """
    bits = np.asarray(bits, dtype=np.uint8).flatten()

    shift_reg = 0
    encoded = np.zeros(len(bits) * 2, dtype=np.uint8)

    for i, b in enumerate(bits):
        bi = int(b)
        b5 = (shift_reg >> 5) & 1
        b4 = (shift_reg >> 4) & 1
        b3 = (shift_reg >> 3) & 1
        b2 = (shift_reg >> 2) & 1
        b1 = (shift_reg >> 1) & 1
        b0 = shift_reg & 1

        # G1 = 0o171: taps at positions 6,5,4,3,0
        g1 = bi ^ b5 ^ b4 ^ b3 ^ b0
        # G2 = 0o133: taps at positions 6,4,3,1,0
        g2 = bi ^ b4 ^ b3 ^ b1 ^ b0

        encoded[i * 2] = g1
        encoded[i * 2 + 1] = g2

        shift_reg = ((shift_reg << 1) | bi) & 0x3F

    return encoded


def convolutional_decode_hard(encoded: np.ndarray) -> np.ndarray:
    """卷积码硬判决译码。"""
    return get_viterbi_decoder().decode_hard(encoded)


def convolutional_decode_soft(llr: np.ndarray) -> np.ndarray:
    """卷积码软判决译码。"""
    return get_viterbi_decoder().decode_soft(llr)


# ── 重复码（调试用）────────────────────────────────────────────


def repetition_encode(bits: np.ndarray, repeat: int = 3) -> np.ndarray:
    """重复编码。"""
    bits = np.asarray(bits, dtype=np.uint8)
    return np.repeat(bits, repeat)


def repetition_decode_hard(encoded: np.ndarray, repeat: int = 3) -> np.ndarray:
    """重复码硬判决（多数投票）。"""
    encoded = np.asarray(encoded, dtype=np.float64)
    n = len(encoded) // repeat
    reshaped = encoded[:n * repeat].reshape(n, repeat)
    decoded = (np.sum(reshaped, axis=1) > repeat / 2).astype(np.uint8)
    return decoded


# ── 分发接口 ──────────────────────────────────────────────────


def encode(bits: np.ndarray, fec_type: FECType = FECType.NONE) -> np.ndarray:
    """统一编码接口。"""
    if fec_type == FECType.NONE:
        return np.asarray(bits, dtype=np.uint8).copy()
    elif fec_type == FECType.REPETITION:
        return repetition_encode(bits)
    elif fec_type == FECType.CONVOLUTIONAL:
        return convolutional_encode(bits)
    else:
        raise ValueError(f"Unknown FEC type: {fec_type}")


def decode_hard(
    encoded: np.ndarray,
    fec_type: FECType = FECType.NONE,
    original_bit_count: int = 0,
) -> np.ndarray:
    """统一硬判决译码接口。"""
    if fec_type == FECType.NONE:
        decoded = np.asarray(encoded, dtype=np.uint8).flatten()
        if original_bit_count > 0:
            decoded = decoded[:original_bit_count]
        return decoded
    elif fec_type == FECType.REPETITION:
        decoded = repetition_decode_hard(encoded)
        if original_bit_count > 0:
            decoded = decoded[:original_bit_count]
        return decoded
    elif fec_type == FECType.CONVOLUTIONAL:
        decoded = convolutional_decode_hard(encoded)
        if original_bit_count > 0:
            decoded = decoded[:original_bit_count]
        return decoded
    else:
        raise ValueError(f"Unknown FEC type: {fec_type}")


def decode_soft(
    llr: np.ndarray,
    fec_type: FECType = FECType.NONE,
    original_bit_count: int = 0,
) -> np.ndarray:
    """统一软判决译码接口。"""
    if fec_type == FECType.NONE:
        # 硬判决
        decoded = (llr <= 0).astype(np.uint8)
        if original_bit_count > 0:
            decoded = decoded[:original_bit_count]
        return decoded
    elif fec_type == FECType.CONVOLUTIONAL:
        decoded = convolutional_decode_soft(llr)
        if original_bit_count > 0:
            decoded = decoded[:original_bit_count]
        return decoded
    else:
        return decode_hard((llr <= 0).astype(np.uint8), fec_type, original_bit_count)
