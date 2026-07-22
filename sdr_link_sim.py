"""
================================================================================
 SDR 全链路仿真 —— 从零讲解每一步数学原理
================================================================================
 test_data.txt → BPSK调制 → RRC脉冲成形 → AWGN信道
 → 匹配滤波 → 前导互相关帧检测 → 符号定时 → BPSK解调
 → CRC校验 → 恢复文件

 运行：python sdr_link_sim.py
 依赖：pip install numpy scipy
================================================================================
"""

import hashlib
import struct
import sys
import zlib
from pathlib import Path

import numpy as np

# ╔══════════════════════════════════════════════════════════════════╗
# ║                    第 0 步：参数定义                              ║
# ╚══════════════════════════════════════════════════════════════════╝

SPS     = 8         # 每符号采样数 (samples per symbol)
ALPHA   = 0.35      # RRC 滚降系数 α
SPAN    = 6         # RRC 滤波器半跨（符号数），总长 = 2*SPAN*SPS + 1
PREAMBLE_LEN = 64   # 前导长度（符号数，也是 PN 序列长度）
GUARD_LEN = 16      # 保护间隔（符号数），帧首帧尾各放 GUARD_LEN*SPS 个 0
SYNC_WORD = 0x1A_CF # 16-bit 同步字，用于验证帧检测正确
SNR_DB    = 20.0    # 仿真信噪比 (dB)，20 dB 几乎无差错
SEED      = 42      # 所有随机过程的固定种子，保证可复现

# 文件路径
INPUT_FILE  = Path(__file__).parent / "test_data.txt"
OUTPUT_FILE = Path(__file__).parent / "decoded_output.txt"

# ╔══════════════════════════════════════════════════════════════════╗
# ║              第 1 步：字节 ↔ 比特互转                            ║
# ╚══════════════════════════════════════════════════════════════════╝

def bytes_to_bits(data: bytes) -> np.ndarray:
    """
    数学：每个字节展开成 8 个比特，MSB（最高位）优先。

    例：byte 0xA3 = 0b10100011
    → bits = [1, 0, 1, 0, 0, 0, 1, 1]

    实现：np.unpackbits 按 MSB-first 展开。
    """
    return np.unpackbits(np.frombuffer(data, dtype=np.uint8))


def bits_to_bytes(bits: np.ndarray) -> bytes:
    """
    逆过程：8 个比特打包成 1 个字节。不足 8 位末尾补 0。
    """
    b = np.asarray(bits, dtype=np.uint8).flatten()
    rem = len(b) % 8
    if rem:
        b = np.pad(b, (0, 8 - rem))
    return np.packbits(b).tobytes()

# ╔══════════════════════════════════════════════════════════════════╗
# ║                 第 2 步：CRC-32 校验                              ║
# ╚══════════════════════════════════════════════════════════════════╝

def crc32_append(data: bytes) -> bytes:
    """
    ┌─────────────────────────────────────────────────────────────┐
    │ 数学原理：CRC = 二进制多项式除法在 GF(2) 上的余数             │
    │                                                                  │
    │ 把 data 视为 GF(2) 多项式 D(x)（每个 bit 是一个系数）。        │
    │ 令 G(x) = x³² + x²⁶ + x²³ + x²² + x¹⁶ + x¹² + x¹¹           │
    │          + x¹⁰ + x⁸ + x⁷ + x⁵ + x⁴ + x² + x + 1             │
    │                                                                  │
    │ 则 CRC-32 = (D(x) · x³²) mod G(x)，是个 32-bit 值。            │
    │                                                                  │
    │ 接收端验证：(D(x)·x³² ⊕ CRC) mod G(x) == 0                     │
    │           → 若为零则数据完整；非零则数据损坏                      │
    │                                                                  │
    │ 检测能力（数学可证）：                                           │
    │   - 所有 1-bit 错误     ✓                                       │
    │   - 所有奇数个 bit 错误 ✓                                       │
    │   - 所有 ≤32-bit 突发错误 ✓                                     │
    │   - 任意 2-bit 错误 99.9999999% 可检测                           │
    └─────────────────────────────────────────────────────────────┘

    实现使用 zlib.crc32（海量验证过的工业标准实现）。
    """
    crc = zlib.crc32(data) & 0xFFFF_FFFF
    return data + struct.pack(">I", crc)


def crc32_verify(data_with_crc: bytes) -> tuple[bytes, bool]:
    """
    接收端：取前 len-4 字节为 payload，末 4 字节为发送方 CRC。
    重新计算 CRC 并与接收到的 CRC 比较。
    """
    if len(data_with_crc) < 4:
        return b"", False
    payload = data_with_crc[:-4]
    received_crc = struct.unpack(">I", data_with_crc[-4:])[0]
    computed_crc = zlib.crc32(payload) & 0xFFFF_FFFF
    return payload, (computed_crc == received_crc)

# ╔══════════════════════════════════════════════════════════════════╗
# ║             第 3 步：BPSK 调制 (Binary Phase Shift Keying)       ║
# ╚══════════════════════════════════════════════════════════════════╝

def bpsk_modulate(bits: np.ndarray) -> np.ndarray:
    """
    ┌───────────────────────────────────────────────────────┐
    │ BPSK 星座映射（最稳健的二元调制）                        │
    │                                                         │
    │   s[k] = 1 - 2 · b[k]     (b[k] ∈ {0, 1})              │
    │                                                         │
    │   b=0  →  s = +1  (相位 0°,   同相)                    │
    │   b=1  →  s = -1  (相位 180°, 反相)                    │
    │                                                         │
    │ 复平面上的星座图：                                       │
    │       Im                                               │
    │       ^                                                │
    │       |    ★ (b=1)          ★ (b=0)                    │
    │       |    -1       0       +1      → Re              │
    │       |                                                │
    │ 判决边界: Re(s) = 0（虚轴）                              │
    │ 最小星座距离 d_min = 2   ← 所有二元调制中最大            │
    │ 每个符号携带 1 bit                                      │
    │ E_s = |s|² = 1                                         │
    └───────────────────────────────────────────────────────┘
    """
    arr = np.asarray(bits, dtype=np.float64)
    return (1.0 - 2.0 * arr).astype(np.complex128)


def bpsk_demodulate_hard(symbols: np.ndarray) -> np.ndarray:
    """
    ┌───────────────────────────────────────────────────────┐
    │ BPSK 硬判决：Re(s) < 0  →  bit=1                      │
    │            Re(s) ≥ 0  →  bit=0                        │
    │                                                         │
    │ 判决阈值 = 0，在 AWGN 下是最优判决（ML 检测）。          │
    └───────────────────────────────────────────────────────┘
    """
    return (np.real(symbols) < 0).astype(np.uint8)


def bpsk_demodulate_soft(symbols: np.ndarray, noise_var: float = 1.0) -> np.ndarray:
    """
    ┌───────────────────────────────────────────────────────┐
    │ BPSK 软判决 (LLR = Log-Likelihood Ratio)               │
    │                                                         │
    │ LLR = ln[ P(b=0|s) / P(b=1|s) ]                       │
    │     = 2 · Re(s) / σ²                                   │
    │                                                         │
    │ LLR > 0 → 更可能是 0；LLR < 0 → 更可能是 1            │
    │ |LLR| 越大 → 置信度越高                                  │
    │                                                         │
    │ 软判决比硬判决多 ~2 dB 增益（给后级 FEC 用时很明显）。    │
    │ 这里保留此函数但仿真先不用 FEC。                         │
    └───────────────────────────────────────────────────────┘
    """
    sigma2 = max(noise_var, 1e-12)
    return 2.0 * np.real(symbols) / sigma2

# ╔══════════════════════════════════════════════════════════════════╗
# ║            第 4 步：RRC 根升余弦脉冲成形                         ║
# ╚══════════════════════════════════════════════════════════════════╝

def design_rrc(spb: int, alpha: float, span: int) -> np.ndarray:
    """
    ┌─────────────────────────────────────────────────────────────┐
    │ RRC (Root Raised Cosine) 滤波器冲激响应                      │
    │                                                              │
    │ h(t) = ┌ sin(πt(1-α)) + 4αt·cos(πt(1+α))                   │
    │        │ ──────────────────────────────────    (一般情况)     │
    │        │    πt·(1 - (4αt)²)                                  │
    │        │                                                     │
    │        ├ 1 - α + 4α/π                         (t=0)          │
    │        │                                                     │
    │        └ (α/√2)·[(1+2/π)sin(π/4α) + (1-2/π)cos(π/4α)]      │
    │                                          (t=±1/(4α))         │
    │                                                              │
    │ 其中归一化符号周期 T=1, α=滚降系数 (0<α≤1)。                  │
    │                                                              │
    │ 【为什么用 RRC？】                                           │
    │ 1. TX·RRC ⊗ RX·RRC = RC (升余弦)，满足 Nyquist 第一准则     │
    │    → 在最佳采样点无码间串扰 (ISI)                             │
    │ 2. RX 端的 RRC 就是匹配滤波器 → 最大化接收 SNR               │
    │ 3. 控制信号带宽 B = (1+α)/Tₛ（本例：1.35/1=1.35×符号率）     │
    │                                                              │
    │ 离散化：t = k/SPS,  k ∈ [-span·SPS, ..., span·SPS]          │
    │ 滤波器长度 = 2·span·SPS + 1                                   │
    └─────────────────────────────────────────────────────────────┘
    """
    t = np.arange(-span, span + 1e-12, 1.0 / spb)
    pi_t = np.pi * t
    four_alpha_t = 4.0 * alpha * t

    denom = pi_t * (1.0 - four_alpha_t ** 2)
    numer = np.sin(pi_t * (1.0 - alpha)) + four_alpha_t * np.cos(pi_t * (1.0 + alpha))

    h = np.zeros_like(t)
    valid = np.abs(denom) >= 1e-12
    h[valid] = numer[valid] / denom[valid]

    # t = 0: 分子分母同时趋于 0，需单独求极限
    idx0 = np.argmin(np.abs(t))
    h[idx0] = 1.0 - alpha + 4.0 * alpha / np.pi

    # t = ±1/(4α): 分母中 (1-(4αt)²) = 0
    t_special_val = 1.0 / (4.0 * alpha)
    idx_s = np.where(np.abs(np.abs(t) - t_special_val) < 1e-6)[0]
    for idx in idx_s:
        h[idx] = (alpha / np.sqrt(2.0)) * (
            (1.0 + 2.0 / np.pi) * np.sin(np.pi / (4.0 * alpha))
            + (1.0 - 2.0 / np.pi) * np.cos(np.pi / (4.0 * alpha))
        )

    # 归一化能量 (∑|h|² = 1)
    energy = np.sum(np.abs(h) ** 2)
    if energy > 0:
        h /= np.sqrt(energy)

    return np.float64(h)


def pulse_shape(symbols: np.ndarray, spb: int, alpha: float, span: int) -> np.ndarray:
    """
    发射端：上采样 + RRC 卷积

    数学：x[n] = Σₖ s[k] · h_rrc[n - k·SPS]
    其中 s[k] 是符号，h_rrc 是 RRC 冲激响应。

    实现：先对符号做插零上采样，再与滤波器做全卷积。
    """
    rrc = design_rrc(spb, alpha, span)
    up = np.zeros(len(symbols) * spb, dtype=np.complex128)
    up[::spb] = symbols
    return np.convolve(up, rrc)


def matched_filter(iq: np.ndarray, spb: int, alpha: float, span: int) -> np.ndarray:
    """
    接收端匹配滤波：与同一 RRC 卷积

    数学：y[n] = Σₖ r[k] · h_rrc[n-k]
    = r ⊗ h_rrc (互相关，但 h_rrc 是实偶函数所以等于卷积)

    去掉首尾各 span·SPS 个采样（滤波器暂态过渡过程）。
    """
    rrc = design_rrc(spb, alpha, span)
    delay = span * spb
    mf = np.convolve(iq, rrc)
    if len(mf) > 2 * delay:
        mf = mf[delay:-delay]
    return mf

# ╔══════════════════════════════════════════════════════════════════╗
# ║               第 5 步：构造物理帧                                ║
# ╚══════════════════════════════════════════════════════════════════╝

def make_preamble_symbols(length: int = PREAMBLE_LEN, seed: int = SEED) -> np.ndarray:
    """
    生成 PN 前导序列（BPSK 符号）。

    ┌───────────────────────────────────────────────────────┐
    │ 前导的作用：                                           │
    │ - 接收端通过互相关找到帧的起始位置                       │
    │ - PN 序列具有近似 δ 函数的自相关：                      │
    │     R[k] = Σₙ p[n]·p[n+k] ≈ N·δ[k]                   │
    │   即仅在 k=0 时出现尖峰，其它位置几乎为零                │
    │   这使得帧检测器能精确锁定帧边界。                       │
    └───────────────────────────────────────────────────────┘
    """
    rng = np.random.default_rng(seed)
    bits = (rng.random(length) > 0.5).astype(np.uint8)
    return bpsk_modulate(bits)


def build_one_frame(payload_bytes: bytes, preamble_syms: np.ndarray,
                    sync_word_bits: np.ndarray) -> np.ndarray:
    """
    ┌───────────────────────────────────────────────────────────┐
    │ 构建一帧的完整 IQ 波形。                                     │
    │                                                              │
    │ 【符号级帧结构】                                              │
    │  0┌─────────┬──────────┬──────┬──────┬─────────┬──────┐     │
    │   │ Guard   │ Preamble │ Sync │ Len  │ Payload │ CRC  │     │
    │   │ 16 sym  │ 64 sym   │16 sym│16 sym│ 变长    │32 sym│     │
    │   └─────────┴──────────┴──────┴──────┴─────────┴──────┘     │
    │   (Guard 放在 IQ 采样级，符号级仅含 Guard 占位,              │
    │    这里我们把所有字段拼在符号级再 RRC ↓)                      │
    │                                                              │
    │ 【IQ 采样级帧结构】                                           │
    │  ┌────────────┬──────────────────────────┬────────────┐     │
    │  │ Guard (IQ) │  全部字段 RRC 成形后     │ Guard (IQ) │     │
    │  │ 16*SPS     │  共 N_total*SPS 采样     │ 16*SPS     │     │
    │  └────────────┴──────────────────────────┴────────────┘     │
    └───────────────────────────────────────────────────────────┘
    """
    # CRC-32 追加
    payload_crc = crc32_append(payload_bytes)            # N + 4 bytes

    # 转比特
    payload_bits = bytes_to_bits(payload_crc)             # (N+4)*8 bits
    len_bits = np.unpackbits(
        np.array([len(payload_bytes)], dtype=">u2").view(np.uint8)
    ).astype(np.uint8)

    # BPSK 调制
    sync_syms  = bpsk_modulate(sync_word_bits)           # 16 syms
    len_syms   = bpsk_modulate(len_bits)                  # 16 syms
    load_syms  = bpsk_modulate(payload_bits)              # (N+4)*8 syms
    guard_syms = np.zeros(GUARD_LEN, dtype=np.complex128) # 16 zero syms

    # 拼接 → RRC 脉冲成形
    sym_seq = np.concatenate([
        guard_syms, preamble_syms, sync_syms, len_syms, load_syms, guard_syms,
    ])
    iq = pulse_shape(sym_seq, SPS, ALPHA, SPAN)

    # 峰值归一化：避免削顶
    peak = float(np.max(np.abs(iq)))
    if peak > 0:
        iq = iq * np.float64(0.5 / peak)

    return np.complex64(iq)

# ╔══════════════════════════════════════════════════════════════════╗
# ║              第 6 步：AWGN 信道模型                              ║
# ╚══════════════════════════════════════════════════════════════════╝

def awgn_channel(tx_iq: np.ndarray, snr_db: float, rng: np.random.Generator) -> np.ndarray:
    """
    ┌──────────────────────────────────────────────────────────────┐
    │ AWGN = Additive White Gaussian Noise                         │
    │                                                               │
    │ 复基带噪声模型：                                               │
    │   n[k] = n_I[k] + j·n_Q[k]                                   │
    │   其中 n_I, n_Q ~ i.i.d N(0, σ²/2)                           │
    │   即每个复样本的能量分布在同相 (I) 和正交 (Q) 两个维度上。      │
    │                                                               │
    │ SNR 定义：                                                    │
    │   SNR_dB = 10·log₁₀(P_signal / P_noise)                      │
    │       →  σ²_total = P_signal / 10^(SNR_dB/10)                │
    │       →  σ²_per_dim = σ²_total / 2                           │
    │                                                               │
    │ BPSK 误码率（无编码，AWGN）：                                   │
    │   P_b = Q(√(2E_b/N₀))                                       │
    │   其中 E_b = 每比特能量, N₀ = 噪声功率谱密度                   │
    │                                                               │
    │ 例：SNR=20dB, 即 E_b/N₀ = 100 → P_b ≈ Q(14.14) ≈ 10⁻⁴⁵       │
    │     (实际上趋近于 0)                                          │
    └──────────────────────────────────────────────────────────────┘
    """
    P_sig = np.mean(np.abs(tx_iq) ** 2)
    sigma2_total = P_sig / (10.0 ** (snr_db / 10.0))
    sigma_per_dim = np.sqrt(sigma2_total / 2.0)

    noise = sigma_per_dim * (
        rng.standard_normal(len(tx_iq))
        + 1j * rng.standard_normal(len(tx_iq))
    )
    return np.complex64(tx_iq + noise)

# ╔══════════════════════════════════════════════════════════════════╗
# ║          第 7 步：接收 - 前导互相关帧检测                        ║
# ╚══════════════════════════════════════════════════════════════════╝

def preamble_correlate(rx_iq: np.ndarray, preamble_syms: np.ndarray) -> np.ndarray:
    """
    ┌──────────────────────────────────────────────────────────────┐
    │ 归一化滑动互相关                                              │
    │                                                               │
    │ 先将前导也做 RRC 成形（因为发射端已经成形过），                 │
    │ 然后用这个成形后的"模板"与接收 IQ 做滑动互相关。               │
    │                                                               │
    │ C[k] = |Σₙ r[k+n] · p_shaped*[n]|                          │
    │        ───────────────────────────────                        │
    │        √(Σₙ|r[k+n]|² · Σₙ|p_shaped[n]|²)                    │
    │                                                               │
    │ 分母是归一化项：                                               │
    │   - 窗口能量：Σₙ|r[k+n]|²（用累积和 O(1) 计算）               │
    │   - 模板能量：Σₙ|p_shaped[n]|²（常量）                        │
    │                                                               │
    │ 归一化后：C[k] ∈ [0, 1]。                                     │
    │         C[k] → 1 表示完美匹配                                  │
    │         C[k] → 0 表示完全不相关                                │
    │                                                               │
    │ 【为什么要在 IQ 采样级做相关而不是在符号级？】                   │
    │  直接在采样级做，不需要先做定时恢复，避免了"蛋鸡问题"。         │
    └──────────────────────────────────────────────────────────────┘
    """
    preamble_shaped = pulse_shape(preamble_syms, SPS, ALPHA, SPAN)
    L = len(preamble_shaped)

    # 滑动窗口功率（累积和，O(1) 窗口计算）
    power = np.abs(rx_iq) ** 2
    cumsum = np.concatenate([[0.0], np.cumsum(power)])
    win_pwr = cumsum[L:] - cumsum[:-L]

    # 互相关
    raw_corr = np.abs(np.correlate(rx_iq, preamble_shaped.conj(), mode="valid"))
    p_energy = np.sum(np.abs(preamble_shaped) ** 2)
    denom = np.sqrt(win_pwr * p_energy)

    corr = np.zeros(len(rx_iq), dtype=np.float64)
    valid_n = len(raw_corr)
    start = L - 1
    corr[start:start + valid_n] = np.divide(
        raw_corr, denom, out=np.zeros(valid_n, dtype=np.float64), where=denom > 1e-12
    )
    return corr


def find_frame_starts(corr_seq: np.ndarray, preamble_shaped_len: int,
                      threshold: float = 0.40) -> list[int]:
    """
    ┌──────────────────────────────────────────────────────────────┐
    │ 峰值检测：在相关序列中找超过门限的局部最大值。                  │
    │                                                               │
    │ 策略（级联门限）：                                             │
    │   1. 绝对门限：C[k] ≥ 0.40（排除纯噪声产生的虚假峰）           │
    │   2. 相对门限：C[k] ≥ 0.70 × Cmax                             │
    │      （排除 payload 内相似比特模式产生的次峰，                   │
    │       次峰一般远小于主峰）                                     │
    │                                                               │
    │ 前导起始 = 峰值位置 - 模板长度 + 1                             │
    │ 帧起始   = 前导起始 - GUARD_LEN*SPS                           │
    │           （因为帧结构是 Guard → Preamble → ...）               │
    └──────────────────────────────────────────────────────────────┘
    """
    peak_max = float(np.max(corr_seq))
    if peak_max < threshold:
        return []

    effective_thr = max(threshold, 0.70 * peak_max)
    L = preamble_shaped_len

    starts = []
    i = 0
    while i < len(corr_seq):
        if corr_seq[i] < effective_thr:
            i += 1
            continue
        # 在该峰附近找局部最大值
        j = i
        limit = min(len(corr_seq), i + L)
        peak_idx = i
        while j < limit and corr_seq[j] >= effective_thr:
            if corr_seq[j] > corr_seq[peak_idx]:
                peak_idx = j
            j += 1
        preamble_start = peak_idx - L + 1
        frame_start = max(0, preamble_start - GUARD_LEN * SPS)
        # 避免重复检测同一帧
        if not starts or frame_start - starts[-1] > L:
            starts.append(frame_start)
        i = max(j, peak_idx + L // 2)

    return starts

# ╔══════════════════════════════════════════════════════════════════╗
# ║       第 8 步：符号定时恢复 + 帧解码                             ║
# ╚══════════════════════════════════════════════════════════════════╝

def decode_frame_at(rx_iq: np.ndarray, frame_iq_start: int,
                    preamble_syms: np.ndarray,
                    sync_word_bits: np.ndarray) -> tuple[bytes | None, dict]:
    """
    ┌──────────────────────────────────────────────────────────────┐
    │ 从帧起始位置提取符号、定最佳采样相位、解调解码。                │
    │                                                               │
    │ 步骤：                                                        │
    │  1. 对接收 IQ 做匹配滤波                                       │
    │  2. 在匹配滤波输出中搜索前导（逐 offset + phase 扫描）          │
    │  3. 找到最佳 offset 和 phase 后，下采样到符号率                 │
    │  4. 跳过 preamble → 验证 sync word → 读长度 → 解 payload → CRC │
    └──────────────────────────────────────────────────────────────┘
    """
    # 匹配滤波
    mf = matched_filter(rx_iq, SPS, ALPHA, SPAN)

    # ================================================================
    # 在 MF 输出中搜索前导的最佳采样位置
    #
    # pulse_shape 输出的 IQ 信号中，前导符号的峰值在
    #   preamble_peak_iq_position = GUARD_LEN*SPS + delay = 128 + 48 = 176
    # 匹配滤波后峰值位置不变（因为 strip delay 只去掉卷积暂态）。
    #
    # 所以我们在 GUARD_LEN*SPS + delay 附近搜索最佳 offset 和 phase。
    # ================================================================

    delay = SPAN * SPS
    # 前导在 MF 输出中的近似位置
    approx_center = frame_iq_start + GUARD_LEN * SPS + delay
    # 在 ±(2*delay) 范围内搜索（足够覆盖 RRC 定时不确定性）
    search_win = 2 * delay

    best_offset = approx_center
    best_phase = 0
    best_dot = -1.0

    lo = max(0, approx_center - search_win)
    hi = min(len(mf) - PREAMBLE_LEN * SPS, approx_center + search_win)
    for off in range(lo, hi):
        for ph in range(SPS):
            cand = mf[off + ph::SPS][:PREAMBLE_LEN]
            d = float(np.abs(np.dot(cand, preamble_syms.conj())))
            if d > best_dot:
                best_dot = d
                best_offset = off
                best_phase = ph

    preamble_iq_start = best_offset + best_phase

    # 用最佳 phase 提取全部符号
    # 帧符号: [Guard:16][Preamble:64][Sync:16][Len:16][Payload...][Guard:16]
    # 前导在符号序列中的位置是 GUARD_LEN (=16)，
    # 对应的 IQ 位置是 preamble_iq_start = best_offset + best_phase
    # 所以 syms_full[0] 对应位置 best_offset + best_phase
    # 我们要跳过 guard (GUARD_LEN 个符号)
    # 即跳过 GUARD_LEN * SPS 个 IQ 样本 = best_offset + best_phase 之前 GUARD_LEN*SPS 个样本
    # 第一个符号(guard)在: preamble_iq_start - GUARD_LEN * SPS
    iq_sym0 = preamble_iq_start - GUARD_LEN * SPS
    while iq_sym0 < 0:
        iq_sym0 += SPS  # 保证非负，可能损失 1 个 guard 符号（无影响）

    syms_full = mf[iq_sym0::SPS]
    syms = syms_full[GUARD_LEN:]  # 跳过 guard
    if len(syms) > GUARD_LEN:
        syms = syms[:-GUARD_LEN]  # 去掉末尾 guard

    info = {"best_offset": best_offset, "best_phase": best_phase,
            "best_dot": best_dot, "preamble_iq_start": preamble_iq_start}

    # ── 字段提取 ──

    # Preamble (64 syms) — 跳过
    pos = PREAMBLE_LEN

    # Sync word (16 bits BPSK → 16 syms)
    if pos + 16 > len(syms):
        return None, info
    rx_sync_bits = bpsk_demodulate_hard(syms[pos:pos + 16])
    pos += 16

    expected_sync = sync_word_bits
    if not np.array_equal(rx_sync_bits, expected_sync):
        info["sync_match"] = False
        info["rx_sync_hex"] = bits_to_bytes(rx_sync_bits)[:2].hex()
        info["exp_sync_hex"] = bits_to_bytes(expected_sync)[:2].hex()
        return None, info
    info["sync_match"] = True

    # Payload length (16 bits BPSK → 16 syms)
    if pos + 16 > len(syms):
        return None, info
    rx_len_bits = bpsk_demodulate_hard(syms[pos:pos + 16])
    pos += 16
    rx_len_bytes = int.from_bytes(bits_to_bytes(rx_len_bits)[:2], "big")

    if rx_len_bytes <= 0 or rx_len_bytes > 10_000_000:
        info["len_invalid"] = True
        return None, info
    info["payload_len"] = rx_len_bytes

    # Payload + CRC: (rx_len_bytes + 4) * 8 bits = (rx_len_bytes + 4) * 8 syms
    payload_crc_bits = (rx_len_bytes + 4) * 8
    if pos + payload_crc_bits > len(syms):
        return None, info
    rx_bits = bpsk_demodulate_hard(syms[pos:pos + payload_crc_bits])
    pos += payload_crc_bits

    data_crc_bytes = bits_to_bytes(rx_bits)
    payload_bytes, crc_ok = crc32_verify(data_crc_bytes)
    info["crc_ok"] = crc_ok

    if not crc_ok:
        return None, info

    return payload_bytes, info

# ╔══════════════════════════════════════════════════════════════════╗
# ║                    第 9 步：主流程                               ║
# ╚══════════════════════════════════════════════════════════════════╝

def main():
    rng = np.random.default_rng(SEED)

    # ─── 初始化 ───
    preamble_syms = make_preamble_symbols(PREAMBLE_LEN, SEED)
    sync_bits = np.unpackbits(
        np.array([SYNC_WORD], dtype=">u2").view(np.uint8)
    ).astype(np.uint8)

    # ─── 1. read file ───
    data = INPUT_FILE.read_bytes()
    print(f"[TX] file: {INPUT_FILE}")
    print(f"     size: {len(data)} bytes")
    print(f"     SHA-256: {hashlib.sha256(data).hexdigest()}")
    print(f"     content:\n{data.decode('utf-8', 'replace')[:120]}")
    print()

    # ─── 2. build frame ───
    frame_iq = build_one_frame(data, preamble_syms, sync_bits)
    print(f"[TX] frame IQ samples: {len(frame_iq)}")
    print(f"     duration: {len(frame_iq) / 2e6 * 1000:.2f} ms @ 2 MHz")
    frame_peak = np.max(np.abs(frame_iq))
    print(f"     peak amplitude: {frame_peak:.3f}")

    total_syms = (GUARD_LEN + PREAMBLE_LEN + 16 + 16 + (len(data) + 4) * 8 + GUARD_LEN)
    print(f"     total symbols: {total_syms} (preamble:{PREAMBLE_LEN} sync:16 len:16 "
          f"payload:{(len(data)+4)*8})")
    print()

    # ─── 3. AWGN channel ───
    rx_iq = awgn_channel(frame_iq, SNR_DB, rng)
    print(f"[CH] AWGN, SNR={SNR_DB} dB")
    print(f"     signal power: {np.mean(np.abs(frame_iq)**2):.4f}")
    noise_power = np.mean(np.abs(rx_iq - frame_iq) ** 2)
    print(f"     noise power: {noise_power:.6f}")
    measured_snr = 10 * np.log10(np.mean(np.abs(frame_iq)**2) / max(noise_power, 1e-20))
    print(f"     measured SNR: {measured_snr:.1f} dB")
    print()

    # ─── 4. preamble correlation ───
    preamble_shaped = pulse_shape(preamble_syms, SPS, ALPHA, SPAN)
    corr = preamble_correlate(rx_iq, preamble_syms)
    corr_peak = float(np.max(corr))
    starts = find_frame_starts(corr, len(preamble_shaped))
    print(f"[RX] preamble correlation peak: {corr_peak:.3f}")
    print(f"     frames detected: {len(starts)}")
    for idx, s in enumerate(starts):
        print(f"     frame {idx+1}: IQ start = {s}")
    print()

    if not starts:
        print("[RX] no frames detected! try lowering threshold or increasing SNR.")
        return

    # ─── 5. decode frames ───
    all_recovered = bytearray()
    for frame_idx, start in enumerate(starts):
        payload, info = decode_frame_at(rx_iq, start, preamble_syms, sync_bits)
        if payload is None:
            print(f"[RX] frame {frame_idx+1} decode FAILED "
                  f"sync_match={info.get('sync_match')} "
                  f"rx_sync={info.get('rx_sync_hex','?')} "
                  f"exp_sync={info.get('exp_sync_hex','?')}")
        else:
            print(f"[RX] frame {frame_idx+1} OK! "
                  f"{len(payload)} bytes, CRC={info.get('crc_ok')}")
            all_recovered.extend(payload)

    # ─── 6. write output ───
    recovered = bytes(all_recovered)
    OUTPUT_FILE.write_bytes(recovered)
    print()
    print(f"[RX] output: {OUTPUT_FILE}")
    print(f"     size: {len(recovered)} bytes")
    print(f"     SHA-256: {hashlib.sha256(recovered).hexdigest()}")
    print()

    # ─── 7. verify ───
    if recovered == data:
        print("=" * 60)
        print("*** BIT-EXACT RECOVERY SUCCESSFUL! ***")
        print("=" * 60)
    else:
        print("=" * 60)
        print(f"FAIL: length {len(recovered)} vs {len(data)}")
        print(f"different bytes: {sum(a != b for a, b in zip(recovered, data))}")
        print("=" * 60)

    # ─── 8. preview ───
    try:
        print(f"\n[RX] recovered content:\n{recovered.decode('utf-8', 'replace')[:120]}")
    except Exception:
        print(f"\n[RX] recovered content (hex): {recovered[:40].hex()}")


if __name__ == "__main__":
    main()
