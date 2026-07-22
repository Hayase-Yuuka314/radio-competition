# operation/09_contest_tx.py
# 正式比赛发射端：读取随机文件 → 组帧 → DSSS扩频 → 发射
"""
用法:
  仿真模式: python operation/09_contest_tx.py --sim --file 随机文件.bin
  真实发射: python operation/09_contest_tx.py --file 随机文件.bin --uri ip:192.168.2.1
"""
import sys, os, time, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np

def main():
    ap = argparse.ArgumentParser(description="正式比赛发射端")
    ap.add_argument("--file", required=True, help="组委会提供的随机文件路径")
    ap.add_argument("--sim", action="store_true", help="仿真模式（无SDR硬件时使用）")
    ap.add_argument("--uri", default="ip:192.168.2.1", help="SDR设备URI")
    ap.add_argument("--mode", choices=["robust","dsss","balanced"], default="dsss",
                    help="发射模式: robust(传统BPSK) / dsss(DSSS扩频) / balanced(传统QPSK)")
    ap.add_argument("--code-length", type=int, default=255, help="DSSS码长")
    ap.add_argument("--team-id", type=int, default=0, help="队伍编号")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--output-dir", default="artifacts/recovered_files")
    args = ap.parse_args()

    # 读取文件
    if not os.path.exists(args.file):
        print(f"文件不存在: {args.file}")
        return 1
    with open(args.file, "rb") as f:
        data = f.read()
    print(f"读取文件: {args.file} ({len(data)} 字节)")

    run_id = time.strftime("%Y%m%d-%H%M%S")
    print(f"Run ID: {run_id}")
    print(f"模式: {args.mode}")
    print()

    if args.mode == "dsss":
        # ---- DSSS 扩频模式 ----
        from wireless_competition.adversarial.frame import dsss_build_frame
        from wireless_competition.adversarial.dsss import SpreadingCodeManager
        from wireless_competition.common.types import FrameMetadata
        from wireless_competition.file_protocol.chunker import chunk_file_with_metadata

        code_mgr = SpreadingCodeManager(our_team_id=args.team_id, code_length=args.code_length)
        code = code_mgr.our_code
        pg = 10 * np.log10(args.code_length)

        print(f"DSSS: 队伍{args.team_id}, 码长{args.code_length}, 增益{pg:.1f}dB")
        print(f"开始发射...")

        chunks = chunk_file_with_metadata(data, file_id=0, block_size=256)
        total_frames = len(chunks)
        tx_start = time.time()

        for fid, seq, total, payload in chunks:
            meta = FrameMetadata(file_id=fid, block_sequence=seq,
                               total_blocks=total, payload_length=len(payload))
            chips = dsss_build_frame(payload, meta, code)

            if args.sim:
                # 仿真模式：保存IQ文件
                out_dir = os.path.join(args.output_dir, run_id)
                os.makedirs(out_dir, exist_ok=True)
                iq_path = os.path.join(out_dir, f"frame_{seq:04d}.npy")
                np.save(iq_path, chips)
            else:
                # 真实SDR发射（需填入实际SDR驱动代码）
                print(f"  [真实发射] 帧{seq+1}/{total_frames}: {len(chips)} chips")
                # sdr.transmit(chips)

        elapsed = time.time() - tx_start
        data_rate = len(data) * 8 / (args.code_length * elapsed) if elapsed > 0 else 0
        print(f"\n发射完成: {total_frames}帧, {elapsed:.1f}s")
        print(f"等效数据率: {data_rate:.0f} bps (扩频因子={args.code_length})")

    else:
        # ---- 传统模式 ----
        from wireless_competition.tx.pipeline import TXPipeline
        from wireless_competition.common.types import ModulationType, FECType

        mod = ModulationType.QPSK if args.mode == "balanced" else ModulationType.BPSK
        tx = TXPipeline(modulation=mod, fec_type=FECType.CONVOLUTIONAL,
                       block_size=256, seed=args.seed)
        frames = tx.process_file(data)

        if args.sim:
            out_dir = os.path.join(args.output_dir, run_id)
            os.makedirs(out_dir, exist_ok=True)
            for i, frm in enumerate(frames):
                np.save(os.path.join(out_dir, f"frame_{i:04d}.npy"), frm)
        print(f"发射完成: {len(frames)}帧")

    # 保存发射日志
    import json
    log = {"run_id": run_id, "file": args.file, "size": len(data),
           "mode": args.mode, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "code_length": args.code_length if args.mode=="dsss" else 0}
    log_path = os.path.join(args.output_dir, run_id, "tx_log.json")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w") as f:
        json.dump(log, f, indent=2)
    print(f"日志: {log_path}")

if __name__ == "__main__":
    sys.exit(main())
