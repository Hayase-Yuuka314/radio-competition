"""DSSS 完整帧结构。

将 DSSS 扩频集成到完整帧（前导/同步字/包头/CRC/分块/重组）。
收发双方共享扩频码，整帧统一扩频解扩。
"""

from __future__ import annotations

import time
from typing import Optional

import numpy as np

from .dsss import spread, despread


# ── 发送端 ──────────────────────────────────────────────────

def dsss_build_frame(
    payload: bytes,
    metadata,  # FrameMetadata
    code: np.ndarray,
    preamble_length_symbols: int = 64,
    guard_length_symbols: int = 16,
    enable_payload_fec: bool = False,  # 载荷是否加卷积码（会翻倍符号数）
) -> np.ndarray:
    """构建完整 DSSS 帧（码片序列）。

    帧结构（符号级）：
        [guard(0)] [preamble] [sync] [header] [pilot] [payload+CRC]

    每个符号被扩频为 code_length 个码片。guard 为 code_length 个零码片。

    Args:
        payload: 有效载荷字节。
        metadata: 帧元数据 (FrameMetadata)。
        code: 扩频码 (±1)。
        preamble_length_symbols: 前导符号数。
        guard_length_symbols: 保护间隔符号数。

    Returns:
        一维 float64 码片序列。
    """
    from ..tx.framing import make_preamble, make_sync_word
    from ..file_protocol.frame_header import encode_header
    from ..file_protocol.integrity import append_crc32
    from ..tx.modulation import bytes_to_bits, bpsk_modulate
    from ..tx.fec import convolutional_encode

    code_len = len(code)

    # 0. 先设置 payload_length（包头编码需要）
    metadata.payload_length = len(payload)

    # 1. 前导符号 (PN BPSK) — 立即转 float64
    preamble_sym = np.real(make_preamble(1, preamble_length_symbols, "pn")).astype(np.float64)

    # 2. 同步字符号 — 立即转 float64
    sync_sym = np.real(make_sync_word()).astype(np.float64)

    # 3. 包头符号 — 立即转 float64
    header_bytes = encode_header(metadata)
    header_bits = bytes_to_bits(header_bytes)
    header_encoded = convolutional_encode(header_bits)
    header_sym = np.real(bpsk_modulate(header_encoded)).astype(np.float64)

    # 4. 导频符号 — 立即转 float64
    pilot_sym = np.real(bpsk_modulate(bytes_to_bits(b"\x55" * 16))).astype(np.float64)

    # 5. 载荷符号 — 可选卷积码 + CRC
    payload_crc = append_crc32(payload)
    payload_bits = bytes_to_bits(payload_crc)
    if enable_payload_fec:
        payload_encoded = convolutional_encode(payload_bits)
        payload_sym = np.real(bpsk_modulate(payload_encoded)).astype(np.float64)
    else:
        payload_sym = np.real(bpsk_modulate(payload_bits)).astype(np.float64)

    # ── 组装符号级帧（全部 float64）──
    frame_symbols = np.concatenate([
        preamble_sym, sync_sym, header_sym, pilot_sym, payload_sym,
    ])

    # ── DSSS 扩频 ──
    chips = spread(frame_symbols, code)

    # ── 添加 guard（code_length 个零码片 × guard_length_symbols）──
    guard_chips = np.zeros(guard_length_symbols * code_len, dtype=np.float64)
    chips = np.concatenate([guard_chips, chips, guard_chips])

    return chips


# ── 接收端 ──────────────────────────────────────────────────

def dsss_receive_frame(
    chips: np.ndarray,
    code: np.ndarray,
    guard_symbols: int = 16,
    sample_rate_hz: float = 2.0e6,
    payload_has_fec: bool = False,  # 载荷是否经过卷积码编码
) -> dict:
    """从 DSSS 码片序列中恢复一帧。

    流程：解扩 → 恢复符号 → 帧检测 → 包头解码 → 载荷提取 → CRC校验。

    Args:
        chips: 接收码片序列。
        code: 扩频码 (±1)。
        guard_symbols: 保护间隔符号数。
        sample_rate_hz: 采样率（仅用于 CFO 估计，DSSS 场景下近似为码片速率）。

    Returns:
        {
            "frame_detected": bool,
            "payload_crc_pass": bool,
            "payload_bytes": bytes,
            "metadata": FrameMetadata or None,
            "failure_reason": str,
        }
    """
    from ..tx.framing import make_preamble, make_sync_word
    from ..file_protocol.frame_header import decode_header, HEADER_LENGTH_BYTES
    from ..file_protocol.integrity import check_crc32
    from ..tx.fec import convolutional_decode_hard
    from ..tx.modulation import bits_to_bytes, bpsk_demodulate_hard

    code_len = len(code)
    preamble_len = 64
    sync_len = 16
    preamble_raw = make_preamble(1, preamble_len, "pn")
    sync_raw = make_sync_word()

    # ── 1. 解扩：码片 → 符号软值 → 硬判 → BPSK 符号 ──
    n_symbols = len(chips) // code_len
    if n_symbols < preamble_len + sync_len + 20:
        return {
            "frame_detected": False,
            "payload_crc_pass": False,
            "payload_bytes": b"",
            "metadata": None,
            "failure_reason": "too_short",
        }

    chips_trimmed = chips[:n_symbols * code_len]
    chips_2d = chips_trimmed.reshape(n_symbols, code_len)
    soft_values = np.dot(chips_2d, code)  # (n_symbols,)

    # 硬判为 BPSK 符号（用于帧检测）
    symbols = (soft_values <= 0).astype(np.float64)  # 1 (bit 1 → -1 in BPSK)
    symbols = 1.0 - 2.0 * symbols  # 0→+1, 1→-1

    # ── 2. 前导定位 ──
    best_pos = 0
    best_dot = -1.0
    for pos in range(guard_symbols - 6, guard_symbols + 12):
        if pos + preamble_len > len(symbols):
            break
        seg = symbols[pos:pos + preamble_len]
        dot = np.abs(np.dot(np.real(seg), np.real(preamble_raw)))
        if dot > best_dot:
            best_dot = dot
            best_pos = pos

    if best_dot < 0.5 * preamble_len:
        return {
            "frame_detected": False,
            "payload_crc_pass": False,
            "payload_bytes": b"",
            "metadata": None,
            "failure_reason": "preamble_not_found",
        }

    # ── 3. 同步字验证 ──
    sync_pos = best_pos + preamble_len
    if sync_pos + sync_len > len(symbols):
        return {
            "frame_detected": False, "payload_crc_pass": False,
            "payload_bytes": b"", "metadata": None,
            "failure_reason": "sync_oob",
        }
    sync_seg = symbols[sync_pos:sync_pos + sync_len]
    sync_dot = np.abs(np.dot(np.real(sync_seg), np.real(sync_raw)))
    if sync_dot < 0.5 * sync_len:
        return {
            "frame_detected": False, "payload_crc_pass": False,
            "payload_bytes": b"", "metadata": None,
            "failure_reason": "sync_mismatch",
        }

    # ── 4. 包头解码 ──
    hdr_start = sync_pos + sync_len
    hdr_sym_count = HEADER_LENGTH_BYTES * 8 * 2  # 224
    if hdr_start + hdr_sym_count > len(symbols):
        return {
            "frame_detected": True, "payload_crc_pass": False,
            "payload_bytes": b"", "metadata": None,
            "failure_reason": "header_oob",
        }

    hdr_syms = symbols[hdr_start:hdr_start + hdr_sym_count]
    hdr_bits_hard = bpsk_demodulate_hard(hdr_syms)
    hdr_decoded = convolutional_decode_hard(hdr_bits_hard)[:HEADER_LENGTH_BYTES * 8]
    hdr_bytes = bits_to_bytes(hdr_decoded)[:HEADER_LENGTH_BYTES]

    try:
        meta, hdr_crc_ok = decode_header(hdr_bytes)
    except Exception:
        return {
            "frame_detected": True, "payload_crc_pass": False,
            "payload_bytes": b"", "metadata": None,
            "failure_reason": "header_parse_error",
        }

    if not hdr_crc_ok:
        return {
            "frame_detected": True, "payload_crc_pass": False,
            "payload_bytes": b"", "metadata": meta,
            "failure_reason": "header_crc_fail",
        }

    # ── 5. 载荷解码 ──
    payload_start = hdr_start + hdr_sym_count + 128  # + pilot
    crc_overhead = 4
    raw_bit_count = (meta.payload_length + crc_overhead) * 8
    if payload_has_fec:
        payload_bit_count = raw_bit_count * 2  # 卷积码 rate 1/2
    else:
        payload_bit_count = raw_bit_count
    payload_end = payload_start + payload_bit_count

    if payload_end > len(symbols):
        payload_bit_count = len(symbols) - payload_start
        if payload_bit_count <= 0:
            return {
                "frame_detected": True, "payload_crc_pass": False,
                "payload_bytes": b"", "metadata": meta,
                "failure_reason": "payload_oob",
            }

    payload_syms = symbols[payload_start:payload_end]
    payload_bits = bpsk_demodulate_hard(payload_syms)[:payload_bit_count]
    if payload_has_fec:
        payload_decoded = convolutional_decode_hard(payload_bits)[:raw_bit_count]
        payload_bytes_all = bits_to_bytes(payload_decoded)
    else:
        payload_bytes_all = bits_to_bytes(payload_bits)
    crc_len = meta.payload_length + crc_overhead

    if len(payload_bytes_all) >= crc_len:
        payload_data, crc_ok = check_crc32(payload_bytes_all[:crc_len])
    else:
        crc_ok = False
        payload_data = b""

    return {
        "frame_detected": True,
        "payload_crc_pass": crc_ok,
        "payload_bytes": payload_data[:meta.payload_length] if crc_ok else b"",
        "metadata": meta,
        "failure_reason": "none" if crc_ok else "payload_crc_fail",
    }


# ── 端到端流水线 ────────────────────────────────────────────

def dsss_frame_end_to_end(
    data: bytes,
    team_id: int = 0,
    code_length: int = 255,
    snr_db: float = 10.0,
    block_size: int = 256,
    seed: int = 42,
) -> dict:
    """DSSS 帧级端到端仿真（含分块和重组）。

    Args:
        data: 原始文件数据。
        team_id: 队伍编号。
        code_length: 扩频码长。
        snr_db: 信噪比。
        block_size: 每块有效载荷字节数。
        seed: 随机种子。

    Returns:
        指标字典。
    """
    from .dsss import SpreadingCodeManager
    from ..file_protocol.chunker import chunk_file_with_metadata
    from ..file_protocol.assembler import FileAssembler
    from ..common.types import FrameMetadata

    rng = np.random.default_rng(seed)
    code_mgr = SpreadingCodeManager(our_team_id=team_id, code_length=code_length)
    code = code_mgr.our_code

    # ── 分块 ──
    chunks = chunk_file_with_metadata(data, file_id=0, block_size=block_size)

    correct_bytes = 0
    total_frames = len(chunks)
    failed_frames = 0
    assembler = FileAssembler()

    for fid, seq, total, payload in chunks:
        meta = FrameMetadata(
            protocol_version=1,
            file_id=fid,
            session_id=0,
            block_sequence=seq,
            total_blocks=total,
            payload_length=len(payload),
        )

        # TX
        chips = dsss_build_frame(payload, meta, code)

        # 信道：AWGN
        signal_power = np.mean(chips ** 2)
        noise_power = signal_power / (10 ** (snr_db / 10))
        noise = np.sqrt(noise_power) * rng.standard_normal(len(chips))
        noisy_chips = chips + noise

        # RX
        result = dsss_receive_frame(noisy_chips, code)

        if result["payload_crc_pass"] and result["metadata"] is not None:
            meta_rx = result["metadata"]
            start = meta_rx.block_sequence * block_size
            end = min(start + len(result["payload_bytes"]), len(data))
            expected = data[start:end]
            correct_bytes += sum(
                1 for a, b in zip(expected, result["payload_bytes"][:len(expected)])
                if a == b
            )
            assembler.accept_raw(
                file_id=meta_rx.file_id,
                block_seq=meta_rx.block_sequence,
                total_blocks=meta_rx.total_blocks,
                payload=result["payload_bytes"],
            )
        else:
            failed_frames += 1

    return {
        "total_frames": total_frames,
        "failed_frames": failed_frames,
        "correct_bytes": correct_bytes,
        "total_bytes": len(data),
        "complete": assembler.is_complete(0),
        "code_length": code_length,
        "processing_gain_db": 10 * np.log10(code_length),
        "snr_db": snr_db,
    }
