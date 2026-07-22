# operation/03_simulate.py
# 端到端通信仿真：发送 → 加噪信道 → 接收
"""用法: python operation/03_simulate.py [SNR_dB] [数据大小]"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np, time
from wireless_competition.tx.pipeline import TXPipeline
from wireless_competition.channel.pipeline import ChannelPipeline
from wireless_competition.rx.sim_receiver import SimulationReceiver
from wireless_competition.file_protocol.assembler import FileAssembler
from wireless_competition.common.types import ModulationType, FECType, ChannelConfig, RxProfile

# 参数（命令行可覆盖）
snr_db = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
data_size = int(sys.argv[2]) if len(sys.argv) > 2 else 1024
mod = ModulationType.QPSK if "--qpsk" in sys.argv else ModulationType.BPSK
fec = FECType.CONVOLUTIONAL if "--fec" in sys.argv else FECType.NONE

print("=" * 50)
print("端到端通信仿真")
print(f"调制={mod.value}  FEC={fec.value}  SNR={snr_db}dB  数据={data_size}B")
print("=" * 50)

# 生成随机文件
data = np.random.default_rng(42).bytes(data_size)

# 发送
t0 = time.time()
tx = TXPipeline(modulation=mod, fec_type=fec, block_size=min(256, data_size), seed=42)
frames = tx.process_file(data)
print(f"\n发送: {len(data)}字节 → {len(frames)}帧, {sum(len(f) for f in frames)}个IQ采样点")

# 信道（加噪声）
channel = ChannelPipeline(ChannelConfig(snr_db=snr_db))
rng = np.random.default_rng(1)

# 接收
rx = SimulationReceiver(profile=RxProfile(modulation=mod, fec_type=fec), seed=42)
assembler = FileAssembler()

correct = 0; failed = 0
for f in frames:
    ch_out = channel.apply(f, 2e6, rng)
    result = rx.process_frame(ch_out.iq, guard_symbols=16)
    if result.payload_crc_pass:
        assembler.accept_raw(0, result.metadata.block_sequence,
                            result.metadata.total_blocks, result.payload_bytes)
        correct += len(result.payload_bytes)
    else:
        failed += 1

elapsed = time.time() - t0

# 结果
print(f"接收: 正确恢复 {correct}/{len(data)} 字节 ({correct/len(data)*100:.1f}%)")
print(f"      失败帧: {failed}/{len(frames)}, 耗时: {elapsed:.2f}s")
print(f"      Goodput: {correct*8/elapsed:.0f} bps")
print(f"      完整收全: {'是' if assembler.is_complete(0) else '否'}")
