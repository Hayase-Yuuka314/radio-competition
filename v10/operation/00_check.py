# operation/00_check.py
# 环境检查：确认所有依赖就绪，跑冒烟测试
"""用法: python operation/00_check.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

print("=" * 50)
print("环境检查")
print("=" * 50)

# 1. Python 版本
print(f"Python: {sys.version.split()[0]}")

# 2. 核心依赖
deps = ["numpy", "scipy", "matplotlib", "sklearn", "yaml", "joblib", "pytest"]
for d in deps:
    try:
        __import__(d)
        print(f"  [OK] {d}")
    except ImportError:
        print(f"  [MISSING] {d}  <- pip install {d}")

# 3. 项目导入
try:
    from wireless_competition.tx.modulation import bpsk_modulate, bpsk_demodulate_hard
    from wireless_competition.tx.fec import convolutional_encode, convolutional_decode_hard
    from wireless_competition.adversarial.dsss import SpreadingCodeManager, spread, despread
    from wireless_competition.common.types import ModulationType, FECType
    print("  [OK] wireless_competition 包导入正常")
except Exception as e:
    print(f"  [FAIL] 包导入失败: {e}")

# 4. 快速功能验证
import numpy as np
bits = np.array([0,1,0,1]*10, dtype=np.uint8)
syms = bpsk_modulate(bits)
rx = bpsk_demodulate_hard(syms)
assert np.array_equal(bits, rx[:len(bits)]), "BPSK往返失败!"
print("  [OK] BPSK调制解调往返正常")

enc = convolutional_encode(bits)
dec = convolutional_decode_hard(enc)[:len(bits)]
assert np.array_equal(bits, dec), "卷积码往返失败!"
print("  [OK] 卷积码编解码往返正常")

mgr = SpreadingCodeManager(our_team_id=0, code_length=127)
chips = spread(bits[:5], mgr.our_code)
rec = despread(chips, mgr.our_code, output_bits=True)
assert np.array_equal(bits[:5], rec[:5]), "DSSS往返失败!"
print("  [OK] DSSS扩频解扩往返正常")

print()
print("环境就绪！")
