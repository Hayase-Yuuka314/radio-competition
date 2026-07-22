# operation/10_contest_rx.py
# 正式比赛接收端：接收IQ �?解扩/解帧 �?CRC校验 �?文件重组 �?保存
"""
用法:
  仿真模式: python operation/10_contest_rx.py --sim --tx-dir artifacts/recovered_files/<run_id>
  真实接收: python operation/10_contest_rx.py --uri usb:2.10.5
"""
import sys, os, time, argparse, json, glob
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np

def main():
    ap = argparse.ArgumentParser(description="正式比赛接收�?)
    ap.add_argument("--sim", action="store_true", help="仿真模式")
    ap.add_argument("--tx-dir", help="发射端输出目录（仿真模式�?)
    ap.add_argument("--uri", default="usb:2.10.5", help="SDR设备URI")
    ap.add_argument("--mode", choices=["robust","dsss","balanced"], default="dsss")
    ap.add_argument("--code-length", type=int, default=255)
    ap.add_argument("--team-id", type=int, default=0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--output-dir", default="artifacts/recovered_files")
    ap.add_argument("--submit-dir", default="artifacts/submission")
    args = ap.parse_args()

    run_id = time.strftime("%Y%m%d-%H%M%S")
    print(f"Run ID: {run_id}")
    print(f"模式: {args.mode}")

    # 公共变量（所有模式共用）
    from wireless_competition.file_protocol.assembler import FileAssembler
    assembler = FileAssembler()
    total_frames = 0
    correct_frames = 0
    rx_start = time.time()

    if args.mode == "dsss":
        # ---- DSSS 解扩接收 ----
        from wireless_competition.adversarial.frame import dsss_receive_frame
        from wireless_competition.adversarial.dsss import SpreadingCodeManager
        from wireless_competition.file_protocol.assembler import FileAssembler

        code_mgr = SpreadingCodeManager(our_team_id=args.team_id, code_length=args.code_length)
        code = code_mgr.our_code

        if args.sim and args.tx_dir:
            # 仿真模式：读取保存的帧文�?            frame_files = sorted(glob.glob(os.path.join(args.tx_dir, "frame_*.npy")))
            print(f"找到 {len(frame_files)} 个帧文件")

            for fpath in frame_files:
                total_frames += 1
                chips = np.load(fpath)
                # 模拟信道：加轻微噪声
                power = np.mean(chips ** 2)
                noise = np.sqrt(power / (10 ** (20 / 10))) * np.random.default_rng(args.seed).standard_normal(len(chips))
                noisy = chips + noise

                result = dsss_receive_frame(noisy, code)
                if result["payload_crc_pass"] and result["metadata"]:
                    assembler.accept_raw(
                        file_id=result["metadata"].file_id,
                        block_seq=result["metadata"].block_sequence,
                        total_blocks=result["metadata"].total_blocks,
                        payload=result["payload_bytes"],
                    )
                    correct_frames += 1
        else:
            print("真实SDR接收模式 �?等待SDR硬件接入")
            # 实际使用时：
            # while not timeout:
            #     iq = sdr.receive(block_size)
            #     result = dsss_receive_frame(iq, code)
            #     ...

    else:
        # ---- 传统接收 ----
        from wireless_competition.rx.sim_receiver import SimulationReceiver
        from wireless_competition.file_protocol.assembler import FileAssembler
        from wireless_competition.common.types import RxProfile, ModulationType, FECType

        mod = ModulationType.QPSK if args.mode == "balanced" else ModulationType.BPSK
        rx = SimulationReceiver(profile=RxProfile(modulation=mod, fec_type=FECType.CONVOLUTIONAL), seed=args.seed)

        if args.sim and args.tx_dir:
            frame_files = sorted(glob.glob(os.path.join(args.tx_dir, "frame_*.npy")))
            for fpath in frame_files:
                total_frames += 1
                frame_iq = np.load(fpath)
                result = rx.process_frame(frame_iq.astype(np.complex128), guard_symbols=16)
                if result.payload_crc_pass:
                    assembler.accept_raw(0, result.metadata.block_sequence,
                                        result.metadata.total_blocks, result.payload_bytes)
                    correct_frames += 1

    elapsed = time.time() - rx_start
    print(f"\n接收完成: {correct_frames}/{total_frames} 帧通过CRC, {elapsed:.1f}s")

    # 重组文件
    if assembler.is_complete(0):
        # 从assembler中重建完整文�?        recovered = bytearray()
        status = assembler.get_status(0)
        if status and status.complete:
            print(f"文件收全! {status.recovered_blocks}/{status.total_blocks} �?)
            # 按序重组
            recovered = bytearray()
            for i in range(status.total_blocks):
                if hasattr(status, '_blocks') and i in status._blocks:
                    recovered.extend(status._blocks[i])
            recovered = bytes(recovered)
        else:
            recovered = b""
            print("警告: 组装状态不完整")
    else:
        missing = assembler.get_missing(0)
        print(f"文件未收�? 缺失 {len(missing)} �? {missing[:5]}...")
        recovered = b""

    # 保存恢复文件
    out_dir = os.path.join(args.output_dir, run_id)
    os.makedirs(out_dir, exist_ok=True)
    recovered_path = os.path.join(out_dir, "recovered.bin")
    with open(recovered_path, "wb") as f:
        f.write(recovered)
    print(f"恢复文件: {recovered_path} ({len(recovered)} 字节)")

    # 准备提交
    submit_dir = os.path.join(args.submit_dir, run_id)
    os.makedirs(submit_dir, exist_ok=True)
    import shutil
    shutil.copy(recovered_path, os.path.join(submit_dir, "recovered.bin"))
    # 同时保存日志
    log = {
        "run_id": run_id, "mode": args.mode, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total_frames": total_frames, "correct_frames": correct_frames,
        "recovered_size": len(recovered),
    }
    with open(os.path.join(submit_dir, "rx_log.json"), "w") as f:
        json.dump(log, f, indent=2)
    print(f"提交目录: {submit_dir}")
    print("请将此目录中�?recovered.bin 按组委会要求提交")

if __name__ == "__main__":
    sys.exit(main())
