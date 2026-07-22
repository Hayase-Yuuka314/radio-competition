"""DSSS 简化端到端链路。

绕过 RRC 帧结构，直接测试 DSSS 核心抗干扰能力。
"""

from __future__ import annotations

import numpy as np

from .dsss import SpreadingCodeManager, spread, despread


def dsss_transmit(
    payload: bytes,
    team_id: int = 0,
    code_length: int = 255,
    seed: int = 42,
) -> np.ndarray:
    """DSSS 发射：payload → BPSK ±1 → 扩频 → 码片。

    Args:
        payload: 有效载荷字节。
        team_id: 队伍编号。
        code_length: 扩频码长。
        seed: 随机种子。

    Returns:
        码片序列（float64，±1）。
    """
    rng = np.random.default_rng(seed)
    code_mgr = SpreadingCodeManager(our_team_id=team_id, code_length=code_length)
    code = code_mgr.our_code

    # 添加 CRC-32
    from ..file_protocol.integrity import append_crc32
    data_with_crc = append_crc32(payload)

    # 字节→比特→BPSK符号
    from ..tx.modulation import bytes_to_bits
    bits = bytes_to_bits(data_with_crc)
    symbols = 1.0 - 2.0 * bits.astype(np.float64)  # 0→+1, 1→-1

    # DSSS 扩频
    chips = spread(symbols, code)
    return chips


def dsss_receive(
    chips: np.ndarray,
    team_id: int = 0,
    code_length: int = 255,
    payload_len: int = 256,
) -> tuple[bytes, bool]:
    """DSSS 接收：码片 → 解扩 → 硬判 → CRC校验。

    Args:
        chips: 接收码片序列。
        team_id: 队伍编号。
        code_length: 扩频码长。
        payload_len: 预期有效载荷长度。

    Returns:
        (有效载荷字节, CRC是否通过)。
    """
    code_mgr = SpreadingCodeManager(our_team_id=team_id, code_length=code_length)
    code = code_mgr.our_code

    # 解扩 → 软值
    soft = despread(chips, code, output_bits=False)

    # 硬判决
    from ..tx.modulation import bits_to_bytes
    bits = (soft <= 0).astype(np.uint8)
    data_bytes = bits_to_bytes(bits)

    # CRC 校验
    from ..file_protocol.integrity import check_crc32
    crc_len = payload_len + 4
    if len(data_bytes) >= crc_len:
        payload_data, crc_ok = check_crc32(data_bytes[:crc_len])
        return payload_data[:payload_len], crc_ok
    return b"", False


def dsss_end_to_end(
    data: bytes,
    team_id: int = 0,
    code_length: int = 255,
    snr_db: float = 10.0,
    seed: int = 42,
) -> dict:
    """一次完整的 DSSS 端到端测试。

    Args:
        data: 原始文件数据。
        team_id: 队伍编号。
        code_length: 扩频码长。
        snr_db: 信噪比 (dB)。
        seed: 随机种子。

    Returns:
        {"correct_bytes": int, "total_bytes": int, "ber": float, "crc_ok": bool}
    """
    rng = np.random.default_rng(seed)

    # TX
    chips = dsss_transmit(data, team_id, code_length, seed)

    # 信道：AWGN
    signal_power = np.mean(chips ** 2)
    noise_power = signal_power / (10 ** (snr_db / 10))
    noise = np.sqrt(noise_power) * rng.standard_normal(len(chips))
    noisy_chips = chips + noise

    # RX
    payload, crc_ok = dsss_receive(noisy_chips, team_id, code_length, len(data))

    correct = 0
    for a, b in zip(data, payload):
        if a == b:
            correct += 1

    return {
        "correct_bytes": correct,
        "total_bytes": len(data),
        "crc_ok": crc_ok,
        "snr_db": snr_db,
        "code_length": code_length,
        "processing_gain_db": 10 * np.log10(code_length),
    }


def dsss_multiteam_end_to_end(
    data: bytes,
    our_team_id: int = 0,
    rival_team_ids: list[int] | None = None,
    code_length: int = 255,
    snr_db: float = 5.0,
    sir_db: float = -10.0,  # 每个对手比我们强多少
    seed: int = 42,
) -> dict:
    """多队同时发射时的 DSSS 端到端测试。

    Args:
        data: 原始文件数据。
        our_team_id: 己方队伍编号。
        rival_team_ids: 对手队伍编号列表。
        code_length: 扩频码长。
        snr_db: 己方信噪比。
        sir_db: 信干比（负值=对手更强）。
        seed: 随机种子。

    Returns:
        指标字典。
    """
    if rival_team_ids is None:
        rival_team_ids = [1, 2, 3]

    rng = np.random.default_rng(seed)
    code_mgr = SpreadingCodeManager(our_team_id=our_team_id, code_length=code_length)

    # 己方信号
    our_chips = dsss_transmit(data, our_team_id, code_length, seed)
    our_power = np.mean(our_chips ** 2)

    # 噪声
    noise_power = our_power / (10 ** (snr_db / 10))
    noise = np.sqrt(noise_power) * rng.standard_normal(len(our_chips))

    # 叠加对手信号
    total = our_chips + noise
    sir_linear = 10 ** (sir_db / 10)

    for rid in rival_team_ids:
        # 每个对手发送随机数据
        rival_data = rng.bytes(len(data))
        rival_chips = dsss_transmit(rival_data, rid, code_length, seed + rid)
        # 功率调整
        rival_power = our_power / sir_linear
        scale = np.sqrt(rival_power / np.mean(rival_chips ** 2))
        # 对齐长度
        min_len = min(len(total), len(rival_chips))
        total[:min_len] += rival_chips[:min_len] * scale

    # 己方接收
    payload, crc_ok = dsss_receive(total, our_team_id, code_length, len(data))

    correct = sum(1 for a, b in zip(data, payload) if a == b)

    return {
        "correct_bytes": correct,
        "total_bytes": len(data),
        "crc_ok": crc_ok,
        "snr_db": snr_db,
        "sir_db": sir_db,
        "n_rivals": len(rival_team_ids),
        "code_length": code_length,
        "processing_gain_db": 10 * np.log10(code_length),
    }
