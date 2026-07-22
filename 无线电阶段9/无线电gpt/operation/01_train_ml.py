# operation/01_train_ml.py
# 一键训练ML干扰分类器
"""用法: python operation/01_train_ml.py"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np
from wireless_competition.ml.dataset import generate_dataset
from wireless_competition.ml.random_forest import InterferenceClassifier

OUTPUT = "artifacts/models/ic_model.joblib"

print("=" * 50)
print("ML干扰分类器 — 一键训练")
print("=" * 50)

# 第1步：生成仿真训练数据（7类干扰 × N组采集 × M个滑动窗口）
print("\n[1/4] 生成仿真训练数据...")
t0 = time.time()
ds = generate_dataset(
    n_captures_per_class=15,     # 每类干扰采集15次
    n_windows_per_capture=10,    # 每次采集滑窗10个样本
    window_samples=512,          # 每样本512个IQ点
    snr_db_range=[-5, 0, 5, 10, 20],  # 覆盖多种信道质量
    seed=42,
)
print(f"  完成: {ds.n_samples} 样本, 7 类干扰, 耗时 {time.time()-t0:.1f}s")
print(f"  类别: {', '.join(ds.unique_labels)}")

# 第2步：划分数据集（按采集分组，零泄漏）
print("\n[2/4] 划分训练/验证/测试集...")
train, val, test = ds.split_by_capture(seed=42)
leak = len(set(train.capture_ids) & set(test.capture_ids))
print(f"  训练: {train.n_samples}  验证: {val.n_samples}  测试: {test.n_samples}")
print(f"  数据泄漏: {leak} 组 (应为0)")

# 第3步：训练随机森林
print("\n[3/4] 训练随机森林分类器...")
t0 = time.time()
clf = InterferenceClassifier(
    n_estimators=80,         # 80棵树
    max_depth=12,            # 最大深度12
    confidence_threshold=0.6, # 置信度<0.6视为OOD
    random_state=42,
)
clf.fit(train)
print(f"  完成, 耗时 {time.time()-t0:.1f}s")

# 第4步：评估 + 保存
print("\n[4/4] 评估效果并保存模型...")
ev = clf.evaluate(test)
print(f"  准确率: {ev['accuracy']:.1%}")
print(f"  Macro F1: {ev['macro_f1']:.3f}")
print(f"  平均置信度: {ev['mean_confidence']:.3f}")
print(f"  OOD触发率: {ev['ood_rate']:.1%}")
print("  各类别 F1 分数:")
for cls, m in sorted(ev["per_class"].items()):
    bar = "#" * int(m["f1"] * 20)
    print(f"    {cls:22s} {m['f1']:.2f} {bar}")

import os as _os
_os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
clf.save(OUTPUT)
print(f"\n模型已保存到: {OUTPUT}")
print(f"文件大小: {os.path.getsize(OUTPUT)/1024:.0f} KB")

# 同时保存特征提取器（确保推理时特征维度一致）
import joblib
ext_path = OUTPUT.replace(".joblib", "_extractor.joblib")
joblib.dump(ds.extractor, ext_path)
print(f"提取器已保存: {ext_path}")
print("\n下一步: python operation/02_use_ml.py")
