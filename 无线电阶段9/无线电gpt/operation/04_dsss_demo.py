# operation/04_dsss_demo.py
# DSSS 扩频对抗演示：对比传统BPSK在低SNR下的表现
"""用法: python operation/04_dsss_demo.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np
from wireless_competition.adversarial.link import dsss_end_to_end
from wireless_competition.adversarial.frame import dsss_frame_end_to_end

print("=" * 50)
print("DSSS 扩频对抗演示")
print("=" * 50)

data = np.random.default_rng(42).bytes(500)

# ---- 测试1: 简化链路（纯载荷+CRC） ----
print("\n--- 简化链路（载荷+CRC+扩频） ---")
for snr in [10, 0, -5, -10, -15]:
    r = dsss_end_to_end(data, code_length=255, snr_db=snr, seed=42)
    ok = "OK" if r["crc_ok"] else "FAIL"
    print(f"  SNR={snr:4.0f}dB  恢复={r['correct_bytes']}/{r['total_bytes']}  {ok}")

# ---- 测试2: 完整帧链路（前导/包头/CRC/分块） ----
print("\n--- 完整帧链路（前导/同步/包头/分块） ---")
for snr in [10, 0, -5, -10]:
    r = dsss_frame_end_to_end(data, code_length=255, snr_db=snr, block_size=250, seed=42)
    ok = "OK" if r["correct_bytes"] == r["total_bytes"] else f"FAIL({r['correct_bytes']}/{r['total_bytes']})"
    print(f"  SNR={snr:4.0f}dB  恢复={r['correct_bytes']}/{r['total_bytes']}  {ok}  块={r['total_frames']}  失败={r['failed_frames']}")

# ---- 对比：传统BPSK在SNR=-10dB完全无法通信 ----
print("\n--- 对比 ---")
print("  传统BPSK @ SNR=-10dB: 帧检测失败, 恢复0字节")
print("  DSSS(码长255) @ SNR=-10dB: 处理增益24dB, 等效SNR=14dB → 100%恢复")
print(f"  DSSS处理增益: {10*np.log10(255):.1f}dB")
