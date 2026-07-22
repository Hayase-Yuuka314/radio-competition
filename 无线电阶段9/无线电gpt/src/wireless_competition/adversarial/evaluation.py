"""对抗效果评估模块。

量化 DSSS 对抗波形的实际效果：
  - 己方解扩后的 BER vs SNR
  - 对手（不知道扩频码）的 BER vs SNR  
  - 处理增益验证
  - 多队场景下的互相关干扰分析
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from .dsss import SpreadingCodeManager, spread, despread


def evaluate_dsss_performance(
    n_bits: int = 10000,
    code_length: int = 1023,
    snr_db_range: list[float] | None = None,
    team_id: int = 0,
    seed: int = 42,
) -> dict:
    """评估 DSSS 在不同 SNR 下的性能。

    对比三组：
      1. 己方（知道扩频码）— 应获得处理增益
      2. 对手（用错误码解扩）— 应接近随机猜测
      3. 无扩频 BPSK 基线 — 作为参照

    Args:
        n_bits: 测试比特数。
        code_length: 扩频码长。
        snr_db_range: SNR 范围。
        team_id: 己方队伍编号。
        seed: 随机种子。

    Returns:
        评估结果字典。
    """
    if snr_db_range is None:
        snr_db_range = [-20, -15, -10, -5, 0, 5, 10, 15, 20]

    rng = np.random.default_rng(seed)
    code_mgr = SpreadingCodeManager(team_id, code_length)
    our_code = code_mgr.our_code
    rival_code = code_mgr.get_rival_code(1)  # 模拟对手 1 的码

    # 生成随机比特
    bits = (rng.random(n_bits) > 0.5).astype(np.uint8)

    # 扩频
    chips = spread(bits, our_code)

    # 对手扩频（模拟对手同时发射）
    rival_bits = (rng.random(n_bits) > 0.5).astype(np.uint8)
    rival_chips = spread(rival_bits, rival_code)

    results = {"snr_db": [], "our_ber": [], "rival_ber": [], "bpsk_baseline_ber": []}

    for snr_db in snr_db_range:
        # 加噪声
        signal_power = np.mean(chips ** 2)
        noise_power = signal_power / (10 ** (snr_db / 10))
        noise_std = np.sqrt(noise_power / 2)
        noise = noise_std * (rng.standard_normal(len(chips)) +
                            1j * rng.standard_normal(len(chips)))

        received = chips + noise.real  # BPSK: 只用实部

        # 己方解扩
        our_decoded = despread(received, our_code, output_bits=True)
        our_errors = np.sum(bits[:len(our_decoded)] != our_decoded)

        # 对手用错误码解扩
        rival_decoded = despread(received, rival_code, output_bits=True)
        rival_errors = np.sum(bits[:len(rival_decoded)] != rival_decoded)

        # BPSK 基线（无扩频，等效于 code_length=1）
        bpsk_symbols = 1.0 - 2.0 * bits.astype(np.float64)
        bpsk_noise = noise_std * rng.standard_normal(len(bpsk_symbols))
        bpsk_received = bpsk_symbols + bpsk_noise
        bpsk_decoded = (bpsk_received <= 0).astype(np.uint8)
        bpsk_errors = np.sum(bits != bpsk_decoded)

        n_decoded = len(our_decoded)
        results["snr_db"].append(snr_db)
        results["our_ber"].append(our_errors / n_decoded if n_decoded > 0 else 0.5)
        results["rival_ber"].append(rival_errors / n_decoded if n_decoded > 0 else 0.5)
        results["bpsk_baseline_ber"].append(bpsk_errors / len(bpsk_decoded))

    # 计算有效 SNR 增益
    results["processing_gain_db"] = 10 * np.log10(code_length)
    results["code_length"] = code_length

    # 找到 BER=0.01 时的 SNR
    results["our_snr_at_1pct_ber"] = _interpolate_snr(
        results["snr_db"], results["our_ber"], 0.01
    )
    results["bpsk_snr_at_1pct_ber"] = _interpolate_snr(
        results["snr_db"], results["bpsk_baseline_ber"], 0.01
    )
    results["effective_gain_db"] = (
        results["bpsk_snr_at_1pct_ber"] - results["our_snr_at_1pct_ber"]
    )

    return results


def evaluate_multiteam_interference(
    n_bits: int = 5000,
    code_length: int = 1023,
    our_team_id: int = 0,
    rival_team_ids: list[int] | None = None,
    snr_db: float = 0.0,
    sir_db: float = -10.0,  # 信干比（对手信号比我们强 10dB）
    seed: int = 42,
) -> dict:
    """模拟多队同时发射时己方的恢复能力。

    场景：我方信号 + N 个对手信号（每个对手用不同扩频码）+ 噪声

    Args:
        n_bits: 测试比特数。
        code_length: 扩频码长。
        our_team_id: 己方编号。
        rival_team_ids: 对手编号列表。
        snr_db: 信噪比（我方信号/噪声）。
        sir_db: 信干比（我方信号/每个对手信号），负值表示对手更强。
        seed: 随机种子。

    Returns:
        评估结果。
    """
    if rival_team_ids is None:
        rival_team_ids = [1, 2, 3]

    rng = np.random.default_rng(seed)
    code_mgr = SpreadingCodeManager(our_team_id, code_length)
    our_code = code_mgr.our_code

    bits = (rng.random(n_bits) > 0.5).astype(np.uint8)
    our_chips = spread(bits, our_code)
    our_power = np.mean(our_chips ** 2)

    # 噪声
    noise_power = our_power / (10 ** (snr_db / 10))
    noise = np.sqrt(noise_power / 2) * rng.standard_normal(len(our_chips))

    # 叠加对手信号
    total_signal = our_chips + noise
    sir_linear = 10 ** (sir_db / 10)
    rival_power_each = our_power / sir_linear

    for rid in rival_team_ids:
        rival_code = code_mgr.get_rival_code(rid)
        rival_bits = (rng.random(n_bits) > 0.5).astype(np.uint8)
        rival_signal = spread(rival_bits, rival_code)
        rival_signal *= np.sqrt(rival_power_each / np.mean(rival_signal ** 2))
        total_signal += rival_signal

    # 己方解扩
    decoded = despread(total_signal, our_code, output_bits=True)
    errors = np.sum(bits[:len(decoded)] != decoded)
    ber = errors / len(decoded) if len(decoded) > 0 else 0.5

    return {
        "our_ber": ber,
        "n_rivals": len(rival_team_ids),
        "snr_db": snr_db,
        "sir_db": sir_db,
        "code_length": code_length,
        "processing_gain_db": 10 * np.log10(code_length),
        "total_errors": int(errors),
        "total_bits": len(decoded),
    }


def _interpolate_snr(
    snr_list: list[float],
    ber_list: list[float],
    target_ber: float,
) -> float:
    """线性插值找到目标 BER 对应的 SNR。"""
    for i in range(len(ber_list) - 1):
        if ber_list[i] >= target_ber >= ber_list[i + 1]:
            # 线性插值
            frac = (target_ber - ber_list[i]) / (ber_list[i + 1] - ber_list[i])
            return snr_list[i] + frac * (snr_list[i + 1] - snr_list[i])
    return float("nan")
