"""多队比赛场景模拟器。

同时模拟多支队伍发射+接收，对比传统 vs DSSS 的 Goodput。
"""

from __future__ import annotations

import time
from typing import Optional

import numpy as np

from ..adversarial.dsss import SpreadingCodeManager
from ..adversarial.link import dsss_end_to_end
from ..common.types import ModulationType, FECType


def simulate_contest(
    n_teams: int = 4,
    data_size: int = 1000,
    snr_db: float = 5.0,
    sir_db: float = 0.0,
    dsss_enabled: list[bool] | None = None,
    dsss_code_length: int = 255,
    seed: int = 42,
) -> dict:
    """模拟多队同时比赛。

    场景：每队发射自己的信号，其他队的信号作为干扰叠加。

    Args:
        n_teams: 队伍数。
        data_size: 每队数据量（字节）。
        snr_db: 信号噪声比。
        sir_db: 信号干扰比（0 = 各队功率相同）。
        dsss_enabled: 每队是否启用 DSSS（None = 全部启用）。
        dsss_code_length: DSSS 码长。
        seed: 随机种子。

    Returns:
        比赛结果字典。
    """
    if dsss_enabled is None:
        dsss_enabled = [True] * n_teams

    rng = np.random.default_rng(seed)
    code_mgr = SpreadingCodeManager(our_team_id=0, code_length=dsss_code_length)

    # 生成每队的数据
    team_data = [rng.bytes(data_size) for _ in range(n_teams)]

    # 生成每队的发射信号（DSSS 码片）
    team_signals = []
    for tid in range(n_teams):
        if dsss_enabled[tid]:
            from ..adversarial.link import dsss_transmit
            team_code = code_mgr.get_rival_code(tid) if tid > 0 else code_mgr.our_code
            from ..adversarial.dsss import SpreadingCodeManager as SCM
            scm = SCM(our_team_id=tid, code_length=dsss_code_length)
            chips = dsss_transmit(team_data[tid], tid, dsss_code_length, seed + tid)
        else:
            # 传统 BPSK（简化）
            from ..tx.modulation import bytes_to_bits, bpsk_modulate
            bits = bytes_to_bits(team_data[tid])
            chips = np.real(bpsk_modulate(bits)).astype(np.float64)

        # 归一化功率
        power = np.mean(chips ** 2)
        chips = chips / np.sqrt(power + 1e-12)
        team_signals.append(chips)

    # 对齐长度到最短
    min_len = min(len(s) for s in team_signals)
    team_signals = [s[:min_len] for s in team_signals]

    # 叠加：每队的接收信号 = 己方信号 + 其他队信号(干扰) + 噪声
    results = []
    for tid in range(n_teams):
        our_signal = team_signals[tid]
        our_power = np.mean(our_signal ** 2)

        # 噪声
        noise_power = our_power / (10 ** (snr_db / 10))
        noise = np.sqrt(noise_power / 2) * (
            rng.standard_normal(min_len) + 1j * rng.standard_normal(min_len)
        )

        # 其他队干扰
        interference = np.zeros(min_len, dtype=np.complex128)
        sir_linear = 10 ** (sir_db / 10)
        for otid in range(n_teams):
            if otid == tid:
                continue
            # 干扰功率 = 己方功率 / SIR
            intf_power = our_power / sir_linear
            scale = np.sqrt(intf_power / (np.mean(np.abs(team_signals[otid]) ** 2) + 1e-12))
            interference += team_signals[otid] * scale

        # 接收信号
        received = our_signal + noise.real + interference.real

        # 解码
        if dsss_enabled[tid]:
            from ..adversarial.link import dsss_receive
            payload, crc_ok = dsss_receive(
                np.real(received).astype(np.float64),
                tid, dsss_code_length, data_size,
            )
        else:
            # 简化传统 BPSK 接收
            from ..tx.modulation import bpsk_demodulate_hard, bits_to_bytes
            rx_bits = bpsk_demodulate_hard(received.astype(np.complex128))
            payload = bits_to_bytes(rx_bits[:data_size * 8])[:data_size]
            crc_ok = (payload == team_data[tid])

        correct = sum(1 for a, b in zip(team_data[tid], payload) if a == b)
        ber = 1.0 - correct / data_size if data_size > 0 else 0.0

        results.append({
            "team_id": tid,
            "dsss_enabled": dsss_enabled[tid],
            "correct_bytes": correct,
            "total_bytes": data_size,
            "ber": ber,
            "crc_ok": crc_ok,
        })

    # 汇总
    dsss_results = [r for r in results if r["dsss_enabled"]]
    trad_results = [r for r in results if not r["dsss_enabled"]]

    return {
        "n_teams": n_teams,
        "snr_db": snr_db,
        "sir_db": sir_db,
        "data_size": data_size,
        "team_results": results,
        "dsss_avg_ber": float(np.mean([r["ber"] for r in dsss_results])) if dsss_results else 0,
        "trad_avg_ber": float(np.mean([r["ber"] for r in trad_results])) if trad_results else 0,
        "dsss_teams_success": sum(1 for r in dsss_results if r["crc_ok"]),
        "trad_teams_success": sum(1 for r in trad_results if r["crc_ok"]),
        "total_dsss_teams": len(dsss_results),
        "total_trad_teams": len(trad_results),
    }
