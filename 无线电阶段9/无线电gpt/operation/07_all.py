# operation/07_all.py
# 一键运行全部
"""用法: python operation/07_all.py"""
import sys, os, subprocess, time

ROOT = os.path.join(os.path.dirname(__file__), "..")
OP = os.path.join(ROOT, "operation")

steps = [
    ("00_check.py",      "环境检查"),
    ("01_train_ml.py",   "ML训练"),
    ("02_use_ml.py",     "ML推理验证"),
    ("03_simulate.py",   "通信仿真"),
    ("04_dsss_demo.py",  "DSSS对抗演示"),
    ("05_visualize.py",  "生成可视化图表"),
    ("06_contest.py",    "多队比赛模拟"),
]

print("=" * 60)
print("一键运行全部")
print("=" * 60)

total_t0 = time.time()
passed = 0
failed = 0

for script, desc in steps:
    path = os.path.join(OP, script)
    if not os.path.exists(path):
        print(f"\n[{desc}] SKIP — 文件不存在")
        continue

    print(f"\n{'='*40}")
    print(f"[{desc}] 运行中...")
    print(f"{'='*40}")
    t0 = time.time()
    result = subprocess.run(
        [sys.executable, path],
        cwd=ROOT,
        capture_output=False,  # 实时输出
    )
    elapsed = time.time() - t0
    if result.returncode == 0:
        print(f"[{desc}] OK ({elapsed:.0f}s)")
        passed += 1
    else:
        print(f"[{desc}] FAILED (code={result.returncode}, {elapsed:.0f}s)")
        failed += 1

total_elapsed = time.time() - total_t0
print(f"\n{'='*60}")
print(f"完成: {passed} 通过, {failed} 失败, 总耗时 {total_elapsed:.0f}s")
print(f"{'='*60}")
