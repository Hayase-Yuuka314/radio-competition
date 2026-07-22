# operation/05_visualize.py
# 一键生成所有可视化图表
"""用法: python operation/05_visualize.py"""
import sys, os, subprocess

ROOT = os.path.join(os.path.dirname(__file__), "..")
SCRIPTS = os.path.join(ROOT, "scripts")

demos = [
    ("demo_waveform.py", "传统通信波形 (4张图)"),
    ("demo_adversarial.py", "DSSS对抗通信 (2张图)"),
    ("demo_ml.py", "ML分类器评估 (1张图)"),
]

print("=" * 50)
print("一键生成所有可视化图表")
print("=" * 50)

for script, desc in demos:
    path = os.path.join(SCRIPTS, script)
    if not os.path.exists(path):
        print(f"  [SKIP] {script} 不存在")
        continue
    print(f"\n>>> {desc}")
    result = subprocess.run(
        [sys.executable, path, "--export"],
        cwd=ROOT,
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(f"  [OK] 已生成")
    else:
        # 警告不影响继续
        lines = [l for l in result.stderr.split("\n") if "UserWarning" not in l and "tight_layout" not in l]
        if any("OK" in l for l in result.stdout.split("\n")):
            print(f"  [OK] 已生成 (有非关键警告)")
        else:
            print(f"  [FAIL] {lines[:2] if lines else 'unknown'}")

print(f"\n图表输出目录: {os.path.join(ROOT, 'artifacts', 'plots')}")
print("文件列表:")
plot_dir = os.path.join(ROOT, "artifacts", "plots")
if os.path.exists(plot_dir):
    for f in sorted(os.listdir(plot_dir)):
        if f.endswith(".png"):
            size = os.path.getsize(os.path.join(plot_dir, f))
            print(f"  {f} ({size//1024} KB)")
