# operation/02_use_ml.py
# 加载已训练模型，演示实时干扰识别
"""用法: python operation/02_use_ml.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np
from wireless_competition.ml.random_forest import InterferenceClassifier
from wireless_competition.features.time_domain import FeatureExtractor
from wireless_competition.channel.pipeline import ChannelPipeline
from wireless_competition.common.types import ChannelConfig, InterferenceFamily
from wireless_competition.tx.modulation import bpsk_modulate

MODEL = "artifacts/models/ic_model.joblib"

# 检查模型是否存在
if not os.path.exists(MODEL):
    print(f"模型文件不存在: {MODEL}")
    print("请先运行: python operation/01_train_ml.py")
    sys.exit(1)

print("=" * 50)
print("ML干扰识别 — 实时推理演示")
print("=" * 50)

# 加载模型和提取器（必须配对）
print(f"\n加载模型: {MODEL}")
clf = InterferenceClassifier.load(MODEL)
import joblib
ext_path = MODEL.replace(".joblib", "_extractor.joblib")
if os.path.exists(ext_path):
    ext = joblib.load(ext_path)
    print(f"加载提取器: {ext_path} (特征维度={ext.n_features})")
else:
    ext = FeatureExtractor(window_samples=512)
    print(f"创建新提取器 (特征维度={ext.n_features})")
print(f"模型就绪, 支持类别: {', '.join(str(c) for c in clf.classes_)}")

# 模拟生成信号
base = np.tile(
    bpsk_modulate((np.random.default_rng(99).random(5000) > 0.5).astype(np.uint8)),
    3
)[:2048].astype(np.complex128)

# 策略映射表（不同干扰→不同应对）
POLICY = {
    "clean":              "信道干净 → 减少FEC冗余, 提高吞吐率",
    "tone":               "单音干扰 → 开启自适应陷波滤波器",
    "multitone":          "多音干扰 → 多级陷波 + 缩窄接收带宽",
    "sweep":              "扫频干扰 → 增强CFO跟踪 + 快速重同步",
    "broadband_noise":    "宽带噪声 → 增强FEC迭代次数 + BPSK回退",
    "bandlimited_noise":  "带限噪声 → 带通滤波 + 避开干扰频段",
    "burst":              "突发干扰 → 深交织 + 短包重传",
    "unknown":            "无法识别 → 回退稳健默认配置",
}

# 测试多种场景
scenarios = [
    ("干净高信噪比", ChannelConfig(snr_db=20, enable_interference=False)),
    ("干净中等信噪比", ChannelConfig(snr_db=10, enable_interference=False)),
    ("单音干扰", ChannelConfig(snr_db=8, enable_interference=True,
                               interference_type=InterferenceFamily.TONE, inr_db=10)),
    ("宽带噪声干扰", ChannelConfig(snr_db=8, enable_interference=True,
                               interference_type=InterferenceFamily.BROADBAND_NOISE, inr_db=10)),
    ("扫频干扰", ChannelConfig(snr_db=8, enable_interference=True,
                               interference_type=InterferenceFamily.SWEEP, inr_db=8)),
    ("极弱信号+干扰", ChannelConfig(snr_db=0, enable_interference=True,
                               interference_type=InterferenceFamily.TONE, inr_db=-5)),
]

print("\n" + "=" * 70)
for name, cfg in scenarios:
    ch = ChannelPipeline(cfg)
    out = ch.apply(base, 2e6, np.random.default_rng(1))
    feat = ext.extract(out.iq[:512])
    result = clf.predict(feat)

    status = "[OK] 可靠" if result["reliable"] else "[??] 不确定 -> 回退默认"
    cls = result["class"]
    action = POLICY.get(cls, POLICY["unknown"])
    print(f"  [{name:14s}] 识别={cls:20s} 置信={result['confidence']:.0%}  {status}")
    print(f"           → {action}")

print("\n说明:")
print("  置信度>=0.6: 模型确定 → 针对性策略")
print("  置信度<0.6:  模型不确定 → 回退保守默认策略（安全第一）")
