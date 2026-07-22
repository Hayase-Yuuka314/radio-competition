"""端到端仿真 CLI。

在纯软件环境中完成 TX → 信道 → RX 全流程。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import time
from pathlib import Path

import numpy as np

from ..channel.pipeline import ChannelPipeline
from ..common.config import config_hash, save_resolved_config
from ..common.logging import get_logger, log_context, setup as setup_logging
from ..common.seeds import set_base_seed
from ..common.types import (
    ChannelConfig,
    DecodeResult,
    FECType,
    ModulationType,
    ProfileID,
    RxProfile,
)
from ..evaluation.metrics import calculate_ber, calculate_goodput_bps, calculate_per
from ..file_protocol.assembler import FileAssembler
from ..rx.pipeline import Receiver
from ..sdr.base import SimulatedSDRDevice
from ..tx.pipeline import TXPipeline


logger = get_logger()


def _random_binary_data(size_bytes: int, seed: int = 0) -> bytes:
    """生成可复现的随机二进制数据。"""
    rng = np.random.default_rng(seed)
    return rng.bytes(size_bytes)


def run_simulation(
    data: bytes,
    tx_pipeline: TXPipeline,
    receiver: Receiver,
    channel: ChannelPipeline,
    sample_rate_hz: float = 2.0e6,
    seed: int = 0,
) -> dict:
    """运行一次完整的仿真。

    Args:
        data: 原始文件数据。
        tx_pipeline: TX 流水线。
        receiver: RX 流水线。
        channel: 信道流水线。
        sample_rate_hz: 采样率。
        seed: 随机种子。

    Returns:
        指标字典。
    """
    t_start = time.perf_counter()
    rng = np.random.default_rng(seed)

    # TX
    frames = tx_pipeline.process_file(data)
    all_iq = tx_pipeline.concat_frames(frames)

    # 信道
    channel_out = channel.apply(all_iq, sample_rate_hz, rng)

    # RX
    results = receiver.process(channel_out.iq, sample_rate_hz)

    # 组装
    assembler = FileAssembler()
    for r in results:
        if r.payload_crc_pass and r.metadata is not None:
            assembler.accept_raw(
                file_id=r.metadata.file_id,
                block_seq=r.metadata.block_sequence,
                total_blocks=r.metadata.total_blocks,
                payload=r.payload_bytes,
            )

    # 指标
    t_elapsed = time.perf_counter() - t_start

    # 恢复的文件
    recovered_blocks = 0
    total_blocks = 0
    correct_payload_bytes = 0
    total_payload_bytes = len(data)

    all_failures = [r.failure_reason.value != "none" for r in results]
    total_frames = len(results)
    failed_frames = sum(1 for r in results if r.failure_reason.value != "none")

    for r in results:
        if r.payload_crc_pass and r.metadata is not None:
            recovered_blocks += 1
            correct_payload_bytes += len(r.payload_bytes)
        if r.metadata is not None:
            total_blocks = max(total_blocks, r.metadata.total_blocks)

    per = calculate_per(total_frames, failed_frames) if total_frames > 0 else 0.0

    # BER (仿真中可用，这里用恢复数据比较)
    recovered = bytearray()
    for r in results:
        if r.payload_crc_pass:
            recovered.extend(r.payload_bytes)
    recovered = bytes(recovered[:len(data)])

    # 计算 BER（逐字节比较）
    byte_errors = sum(
        1 for a, b in zip(data, recovered)
        if a != b
    )
    ber = byte_errors / max(len(data), 1)

    goodput = calculate_goodput_bps(min(correct_payload_bytes, total_payload_bytes), t_elapsed)

    return {
        "ber": ber,
        "per": per,
        "goodput_bps": goodput,
        "recovered_blocks": recovered_blocks,
        "total_blocks": max(total_blocks, 1),
        "failed_frames": failed_frames,
        "total_frames": total_frames,
        "correct_bytes": min(correct_payload_bytes, total_payload_bytes),
        "total_bytes": total_payload_bytes,
        "elapsed_time_s": t_elapsed,
        "seed": seed,
    }


def main():
    parser = argparse.ArgumentParser(description="Wireless Competition Simulation")
    parser.add_argument("--data-size", type=int, default=1024,
                        help="Random data size in bytes (default: 1024)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Base random seed")
    parser.add_argument("--snr-db", type=float, default=30.0,
                        help="SNR in dB")
    parser.add_argument("--cfo-hz", type=float, default=0.0,
                        help="CFO in Hz")
    parser.add_argument("--modulation", type=str, default="bpsk",
                        choices=["bpsk", "qpsk"],
                        help="Modulation type")
    parser.add_argument("--fec", type=str, default="none",
                        choices=["none", "repetition", "convolutional"],
                        help="FEC type")
    parser.add_argument("--output-dir", type=str, default="artifacts/reports/latest",
                        help="Output directory for reports")
    parser.add_argument("--verbose", action="store_true",
                        help="Verbose output")

    args = parser.parse_args()

    # 日志
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(level=getattr(__import__('logging'), log_level))

    set_base_seed(args.seed)
    logger.info(f"Simulation seed={args.seed}, data_size={args.data_size}B")

    # 生成数据
    data = _random_binary_data(args.data_size, args.seed)

    mod_map = {"bpsk": ModulationType.BPSK, "qpsk": ModulationType.QPSK}
    fec_map = {"none": FECType.NONE, "repetition": FECType.REPETITION,
               "convolutional": FECType.CONVOLUTIONAL}

    modulation = mod_map[args.modulation]
    fec_type = fec_map[args.fec]

    # TX
    tx = TXPipeline(
        modulation=modulation,
        fec_type=fec_type,
        block_size=args.data_size,  # 单块传输
        seed=args.seed,
    )

    # 信道
    ch_config = ChannelConfig(snr_db=args.snr_db, cfo_hz=args.cfo_hz)
    channel = ChannelPipeline(ch_config)

    # RX
    rx_profile = RxProfile(
        modulation=modulation,
        fec_type=fec_type,
        profile_id=ProfileID.P1_ROBUST,
    )
    receiver = Receiver(profile=rx_profile, seed=args.seed)

    # 运行
    metrics = run_simulation(data, tx, receiver, channel, seed=args.seed)

    # 输出
    logger.info(f"BER: {metrics['ber']:.6f}")
    logger.info(f"PER: {metrics['per']:.4f}")
    logger.info(f"Goodput: {metrics['goodput_bps']:.1f} bps")
    logger.info(f"Recovered: {metrics['correct_bytes']}/{metrics['total_bytes']} bytes")
    logger.info(f"Elapsed: {metrics['elapsed_time_s']:.3f}s")

    # 保存报告
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    import json
    with open(out / "metrics.json", "w") as f:
        json.dump(metrics, f, indent=2, default=str)

    logger.info(f"Report saved to {out / 'metrics.json'}")

    return 0 if metrics["ber"] == 0 else 1


if __name__ == "__main__":
    exit(main())
