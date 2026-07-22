# operation/11_contest_e2e.py
# 竞赛一条龙：生成随机文件 → TX发射 → 信道 → RX接收 → 比对正确性
"""用法: python operation/11_contest_e2e.py [--size 10000] [--mode dsss] [--snr 10]"""
import sys, os, time, argparse, json, hashlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np

def main():
    ap = argparse.ArgumentParser(description="竞赛一条龙端到端演练")
    ap.add_argument("--size", type=int, default=5000, help="模拟文件大小(字节)")
    ap.add_argument("--mode", choices=["robust","dsss","balanced"], default="dsss")
    ap.add_argument("--snr", type=float, default=10.0, help="仿真信噪比(dB)")
    ap.add_argument("--code-length", type=int, default=255)
    ap.add_argument("--team-id", type=int, default=0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--output-dir", default="artifacts/contest_runs")
    args = ap.parse_args()

    run_id = time.strftime("%Y%m%d-%H%M%S")
    out_dir = os.path.join(args.output_dir, run_id)
    os.makedirs(out_dir, exist_ok=True)

    print("=" * 60)
    print("竞赛一条龙端到端演练")
    print(f"Run ID: {run_id}")
    print(f"模式: {args.mode}  SNR: {args.snr}dB  大小: {args.size}B")
    print("=" * 60)

    # ---- Step 1: 生成模拟随机文件 ----
    print("\n[1/5] 生成模拟随机文件...")
    rng = np.random.default_rng(args.seed)
    data = rng.bytes(args.size)
    file_path = os.path.join(out_dir, "random_file.bin")
    with open(file_path, "wb") as f:
        f.write(data)
    print(f"  文件: {file_path} ({len(data)} 字节)")

    # ---- Step 2: TX 发射 ----
    print(f"\n[2/5] 发射端处理...")
    t0 = time.time()

    if args.mode == "dsss":
        from wireless_competition.adversarial.frame import dsss_build_frame
        from wireless_competition.adversarial.dsss import SpreadingCodeManager
        from wireless_competition.common.types import FrameMetadata
        from wireless_competition.file_protocol.chunker import chunk_file_with_metadata

        code_mgr = SpreadingCodeManager(our_team_id=args.team_id, code_length=args.code_length)
        code = code_mgr.our_code
        pg = 10 * np.log10(args.code_length)

        chunks = chunk_file_with_metadata(data, file_id=0, block_size=256)
        all_frames = []
        for fid, seq, total, payload in chunks:
            meta = FrameMetadata(file_id=fid, block_sequence=seq,
                               total_blocks=total, payload_length=len(payload))
            chips = dsss_build_frame(payload, meta, code)
            all_frames.append(chips)

        print(f"  DSSS: {len(all_frames)}帧, 码长{args.code_length}, 增益{pg:.1f}dB")
    else:
        from wireless_competition.tx.pipeline import TXPipeline
        from wireless_competition.common.types import ModulationType, FECType
        mod = ModulationType.QPSK if args.mode == "balanced" else ModulationType.BPSK
        tx = TXPipeline(modulation=mod, fec_type=FECType.CONVOLUTIONAL,
                       block_size=256, seed=args.seed)
        all_frames = tx.process_file(data)
        print(f"  传统: {len(all_frames)}帧")

    # ---- Step 3: 信道 ----
    print(f"\n[3/5] 信道传输 (SNR={args.snr}dB)...")
    from wireless_competition.channel.pipeline import ChannelPipeline
    from wireless_competition.common.types import ChannelConfig
    channel = ChannelPipeline(ChannelConfig(snr_db=args.snr))
    ch_rng = np.random.default_rng(args.seed + 1)

    received_frames = []
    for f in all_frames:
        ch_out = channel.apply(
            f.astype(np.complex128) if f.dtype != np.complex128 else f,
            2e6, ch_rng,
        )
        received_frames.append(ch_out.iq)

    # ---- Step 4: RX 接收 ----
    print(f"\n[4/5] 接收端恢复...")
    from wireless_competition.file_protocol.assembler import FileAssembler
    assembler = FileAssembler()
    total_frames = 0
    correct_frames = 0

    if args.mode == "dsss":
        from wireless_competition.adversarial.frame import dsss_receive_frame
        for rf in received_frames:
            total_frames += 1
            # 转实数用于DSSS
            chips_real = np.real(rf).astype(np.float64) if np.iscomplexobj(rf) else rf
            result = dsss_receive_frame(chips_real, code)
            if result["payload_crc_pass"] and result["metadata"]:
                assembler.accept_raw(
                    file_id=result["metadata"].file_id,
                    block_seq=result["metadata"].block_sequence,
                    total_blocks=result["metadata"].total_blocks,
                    payload=result["payload_bytes"],
                )
                correct_frames += 1
    else:
        from wireless_competition.rx.sim_receiver import SimulationReceiver
        from wireless_competition.common.types import RxProfile, ModulationType, FECType
        mod = ModulationType.QPSK if args.mode == "balanced" else ModulationType.BPSK
        rx = SimulationReceiver(profile=RxProfile(modulation=mod, fec_type=FECType.CONVOLUTIONAL), seed=args.seed)
        for rf in received_frames:
            total_frames += 1
            result = rx.process_frame(rf.astype(np.complex128), guard_symbols=16)
            if result.payload_crc_pass and result.metadata:
                assembler.accept_raw(0, result.metadata.block_sequence,
                                    result.metadata.total_blocks, result.payload_bytes)
                correct_frames += 1

    print(f"  帧通过率: {correct_frames}/{total_frames}")

    # ---- Step 5: 比对结果 ----
    print(f"\n[5/5] 正确性验证...")
    status = assembler.get_status(0)
    if status and status.complete and hasattr(status, '_blocks'):
        recovered = bytearray()
        for i in range(status.total_blocks):
            if i in status._blocks:
                recovered.extend(status._blocks[i])
        recovered = bytes(recovered)
    else:
        recovered = b""

    # 计算 BER（逐比特比较，而非逐字节zip）
    data_bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))
    if len(recovered) > 0:
        recovered_bits = np.unpackbits(np.frombuffer(recovered[:len(data)], dtype=np.uint8))
        min_len = min(len(data_bits), len(recovered_bits))
        bit_errors = int(np.sum(data_bits[:min_len] != recovered_bits[:min_len]))
        # 缺失的比特也算错误
        bit_errors += abs(len(data_bits) - len(recovered_bits))
        total_bits = max(len(data_bits), len(recovered_bits))
        ber = bit_errors / total_bits if total_bits > 0 else 1.0
    else:
        bit_errors = len(data_bits)
        ber = 1.0

    # 长度差
    byte_errors = abs(len(data) - len(recovered))
    for i in range(min(len(data), len(recovered))):
        if data[i] != recovered[i]:
            byte_errors += 1

    # SHA-256 校验
    sha_ok = hashlib.sha256(data).hexdigest() == hashlib.sha256(recovered).hexdigest() if len(recovered) == len(data) else False

    # 保存
    with open(os.path.join(out_dir, "recovered.bin"), "wb") as f:
        f.write(recovered)

    # 计算波形持续时间（而非Python运行时间）
    if args.mode == "dsss":
        total_chips = sum(len(f) for f in all_frames)
        waveform_duration = total_chips / (2e6)  # 码片速率 ≈ 采样率
    else:
        total_samples = sum(len(f) for f in all_frames)
        waveform_duration = total_samples / (2e6)
    goodput = len(data) * 8 / waveform_duration if waveform_duration > 0 else 0

    # 结果
    elapsed = time.time() - t0
    print(f"  原始文件: {len(data)} 字节 (SHA256={hashlib.sha256(data).hexdigest()[:16]}...)")
    print(f"  恢复文件: {len(recovered)} 字节 (SHA256={hashlib.sha256(recovered).hexdigest()[:16]}...)" if len(recovered)>0 else "  恢复文件: 0 字节 (空!)")
    print(f"  组装完成: {status.complete if status else False}")
    print(f"  字节错误: {byte_errors}")
    print(f"  比特BER:  {ber:.6f}")
    print(f"  SHA-256匹配: {sha_ok}")
    print(f"  波形时长: {waveform_duration:.3f}s")
    print(f"  Goodput:  {goodput:.0f} bps (波形持续时间内正确交付的有效载荷)")
    print(f"  Python耗时: {elapsed:.1f}s (仅供参考, 不等于空口时间)")

    # 保存报告
    report = {
        "run_id": run_id, "mode": args.mode, "snr_db": args.snr,
        "file_size": len(data), "recovered_size": len(recovered),
        "byte_errors": byte_errors, "bit_ber": ber,
        "sha256_match": sha_ok, "assembly_complete": status.complete if status else False,
        "total_frames": total_frames, "correct_frames": correct_frames,
        "code_length": args.code_length if args.mode=="dsss" else 0,
        "waveform_duration_s": waveform_duration, "goodput_bps": goodput,
        "python_elapsed_s": elapsed, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with open(os.path.join(out_dir, "report.json"), "w") as f:
        json.dump(report, f, indent=2)

    # PASS条件：SHA匹配 + 组装完成 + 无误码
    passed = sha_ok and (status.complete if status else False) and byte_errors == 0
    status_icon = "[PASS]" if passed else "[FAIL]"
    print(f"\n{status_icon} 报告: {os.path.join(out_dir, 'report.json')}")
    return 0 if passed else 1

if __name__ == "__main__":
    sys.exit(main())
