#!/usr/bin/env python
"""ML 干扰分类器可视化。用法: python scripts/demo_ml.py [--export]"""
import sys; sys.path.insert(0, "src")
import numpy as np
import matplotlib; matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from pathlib import Path

from wireless_competition.ml.dataset import generate_dataset
from wireless_competition.ml.random_forest import InterferenceClassifier

plt.rcParams["font.sans-serif"]=["SimHei","Microsoft YaHei","DejaVu Sans"]
plt.rcParams["axes.unicode_minus"]=False

def plot_classifier_report():
    print("Generating dataset...")
    ds = generate_dataset(n_captures_per_class=12, n_windows_per_capture=12,
                          window_samples=512, snr_db_range=[0,5,10,20], seed=42)
    train,val,test = ds.split_by_capture(seed=42)
    clf = InterferenceClassifier(n_estimators=80, max_depth=12)
    clf.fit(train)
    ev = clf.evaluate(test)
    fi = clf._rf.feature_importances_
    names = clf._rf.feature_names_in_ if hasattr(clf._rf,'feature_names_in_') else \
            [f'f{i}' for i in range(len(fi))]
    # Use extractor names
    ext = train.extractor
    if hasattr(ext, 'feature_names') and ext._feature_names:
        names = ext._feature_names

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    # A) 混淆矩阵
    ax = axes[0]
    cm = np.array(ev["confusion_matrix"])
    im = ax.imshow(cm, cmap="RdYlGn", vmin=0, vmax=np.max(cm))
    cls_names = ev["class_names"]
    ax.set_xticks(range(len(cls_names))); ax.set_yticks(range(len(cls_names)))
    ax.set_xticklabels([c[:6] for c in cls_names], fontsize=7, rotation=45)
    ax.set_yticklabels(cls_names, fontsize=7)
    for i in range(len(cls_names)):
        for j in range(len(cls_names)):
            ax.text(j,i,str(cm[i,j]),ha="center",va="center",fontsize=8,
                    color="white" if cm[i,j]>np.max(cm)/2 else "black")
    ax.set_title(f"混淆矩阵 (Acc={ev['accuracy']:.2f})", fontsize=12, fontweight="bold")
    ax.set_xlabel("预测"); ax.set_ylabel("真实")
    plt.colorbar(im, ax=ax, shrink=0.8)

    # B) 特征重要性 Top15
    ax = axes[1]
    idx = np.argsort(fi)[-15:]
    bars = ax.barh(range(15), fi[idx], color="#FF9800", edgecolor="black", linewidth=0.5)
    short_names = [n[:30] for n in np.array(names)[idx]]
    ax.set_yticks(range(15)); ax.set_yticklabels(short_names, fontsize=6)
    ax.set_title("特征重要性 Top 15", fontsize=12, fontweight="bold")
    ax.set_xlabel("重要性")
    ax.grid(True, alpha=0.3, axis="x")

    # C) 每类F1
    ax = axes[2]
    cls_list = sorted(ev["per_class"].keys())
    f1s = [ev["per_class"][c]["f1"] for c in cls_list]
    colors = ["#4CAF50" if f>0.8 else "#FF9800" if f>0.5 else "#F44336" for f in f1s]
    ax.bar(cls_list, f1s, color=colors, edgecolor="black", linewidth=0.5)
    ax.set_title(f"每类 F1 (Macro={ev['macro_f1']:.2f})", fontsize=12, fontweight="bold")
    ax.set_ylabel("F1 Score"); ax.set_ylim(0, 1.1)
    ax.tick_params(axis="x", rotation=45, labelsize=7)
    ax.axhline(y=0.8, color="green", linestyle="--", alpha=0.3)
    ax.grid(True, alpha=0.3, axis="y")

    fig.suptitle(f"干扰分类器评估 — {len(cls_list)}类 随机森林 ({clf._rf.n_estimators}棵树)",
                 fontsize=14, fontweight="bold")
    fig.tight_layout()
    return fig


def export_all(output_dir="artifacts/plots"):
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    matplotlib.use("Agg")
    fig = plot_classifier_report()
    path = out / "ml_01_classifier_report.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  [OK] {path}")

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", action="store_true")
    args = ap.parse_args()
    if args.export:
        export_all()
    else:
        fig = plot_classifier_report()
        plt.show()
