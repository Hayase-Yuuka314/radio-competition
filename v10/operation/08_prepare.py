# operation/08_prepare.py
# 赛前准备清单：环境冻结、模型校验、硬件检查
"""用法: python operation/08_prepare.py"""
import sys, os, hashlib, time, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

ROOT = os.path.join(os.path.dirname(__file__), "..")

print("=" * 60)
print("赛前准备清单")
print("=" * 60)

checks = []

# 1. 检查配置文件
print("\n[1] 配置文件检查...")
import yaml
rules_path = os.path.join(ROOT, "configs", "contest_rules.yaml")
with open(rules_path, "r", encoding="utf-8") as f:
    rules = yaml.safe_load(f)

null_fields = []
for section in ["rules", "rf", "hardware"]:
    for k, v in rules.get(section, {}).items():
        if v is None:
            null_fields.append(f"{section}.{k}")

if null_fields:
    print(f"  [WARN] {len(null_fields)} 个字段未填写:")
    for nf in null_fields[:5]:
        print(f"         {nf}")
    print(f"  -> 纯软件仿真可用，空口发射被阻止")
else:
    print(f"  [OK] 规则字段全部填写")

# 2. 检查模型文件
print("\n[2] 模型文件检查...")
model_path = os.path.join(ROOT, "artifacts", "models", "ic_model.joblib")
if os.path.exists(model_path):
    size = os.path.getsize(model_path)
    with open(model_path, "rb") as f:
        md5 = hashlib.md5(f.read()).hexdigest()
    print(f"  [OK] ic_model.joblib ({size//1024}KB, MD5={md5[:12]}...)")
    checks.append(("model", md5[:12]))
else:
    print(f"  [WARN] 模型不存在，运行: python operation/01_train_ml.py")

# 3. 磁盘空间
print("\n[3] 磁盘空间检查...")
free_gb = shutil.disk_usage(ROOT).free / (1024**3)
status = "OK" if free_gb > 5 else "WARN"
print(f"  [{status}] 剩余 {free_gb:.1f} GB (建议>5GB)")

# 4. 依赖列表
print("\n[4] 依赖冻结...")
try:
    import pkg_resources
    pkgs = sorted([f"{d.project_name}=={d.version}" for d in pkg_resources.working_set
                   if d.project_name in ["numpy","scipy","matplotlib","scikit-learn","pandas","pyyaml","joblib","pytest"]])
    for p in pkgs:
        print(f"  {p}")
    checks.append(("deps", len(pkgs)))
except:
    print("  [WARN] 无法获取依赖版本")

# 5. SDR 硬件检查（如果有）
print("\n[5] SDR 硬件检查...")
try:
    import adi
    print("  [OK] pyadi-iio 可用 (PlutoSDR/NanoSDR)")
    checks.append(("sdr", "adi"))
except ImportError:
    print("  [INFO] pyadi-iio 未安装 (无SDR硬件时正常)")
    checks.append(("sdr", "simulated"))

# 6. 生成校验和文件
print("\n[6] 生成校验和...")
manifest = {
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "checks": checks,
}
import json
manifest_path = os.path.join(ROOT, "artifacts", "contest_manifest.json")
os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
with open(manifest_path, "w") as f:
    json.dump(manifest, f, indent=2, default=str)
print(f"  [OK] {manifest_path}")

print("\n" + "=" * 60)
print("检查完成")
print("=" * 60)
print("\n赛前操作清单:")
print("  [ ] 确认比赛规则已填入 configs/contest_rules.yaml")
print("  [ ] 模型已训练: python operation/01_train_ml.py")
print("  [ ] 两台电脑均跑通: python operation/03_simulate.py")
print("  [ ] 准备离线依赖包")
print("  [ ] 记录SDR设备URI")
print("  [ ] 禁用自动更新和休眠")
print("  [ ] 备份全部代码+模型到U盘")
