#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
DSSS对抗通信可视化演示
=======================
展示直接序列扩频的核心原理和对抗效果。

用法：python scripts/demo_adversarial.py [--export]
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

from wireless_competition.adversarial.dsss import (
    SpreadingCodeManager, spread, despread,
    generate_gold_code, processing_gain_db,
)
from wireless_competition.adversarial.waveform import AdversarialWaveform
from wireless_competition.adversarial.evaluation import (
    evaluate_dsss_performance,
    evaluate_multiteam_interference,
)
from wireless_competition.adversarial.strategy import AdversarialController

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

CODE_LENGTH = 255
RNG = np.random.default_rng(42)


def _make_noise(signal: np.ndarray, snr_db: float = 5.0) -> np.ndarray:
    """生成 AWGN 噪声，功率匹配 SNR。"""
    power = np.mean(signal ** 2)
    noise_power = power / (10 ** (snr_db / 10))
    return np.sqrt(noise_power) * RNG.standard_normal(len(signal))


def plot_dsss_principle():
    """图1：DSSS扩频解扩原理（6面板）。"""
    fig = plt.figure(figsize=(16, 9))
    gs = GridSpec(3, 3, figure=fig, hspace=0.5, wspace=0.35)

    code_mgr = SpreadingCodeManager(our_team_id=0, code_length=CODE_LENGTH)
    our_code = code_mgr.our_code
    rival_code = code_mgr.get_rival_code(1)

    # 生成一小段信号做演示
    n_demo_bits = 8
    demo_bits = np.array([0, 1, 0, 0, 1, 1, 0, 1], dtype=np.uint8)
    chips = spread(demo_bits, our_code)                        # 干净码片
    chips_noisy = chips + _make_noise(chips, snr_db=5.0)      # 加噪码片（SNR=5dB）

    # A) 原始比特
    ax = fig.add_subplot(gs[0, 0])
    ax.step(range(n_demo_bits), demo_bits, where="mid", linewidth=2, color="#2196F3")
    ax.set_title("原始发送比特 (8 bits)", fontsize=11, fontweight="bold")
    ax.set_ylim(-0.2, 1.2); ax.set_yticks([0, 1])
    ax.set_xlabel("比特序号"); ax.set_ylabel("值")
    ax.grid(True, alpha=0.3)

    # B) 扩频码
    ax = fig.add_subplot(gs[0, 1])
    ax.step(range(min(100, CODE_LENGTH)), our_code[:100],
            where="mid", linewidth=0.8, color="#FF9800")
    ax.set_title(f"己方扩频码 (前100位/{CODE_LENGTH})", fontsize=11, fontweight="bold")
    ax.set_ylim(-1.3, 1.3); ax.set_yticks([-1, 0, 1])
    ax.set_xlabel("码片序号"); ax.set_ylabel("±1")
    ax.grid(True, alpha=0.3)

    # C) 扩频后码片—干净 vs 加噪（前2比特）
    ax = fig.add_subplot(gs[0, 2])
    show_chips = 2 * CODE_LENGTH
    ax.plot(range(show_chips), chips[:show_chips], linewidth=0.8, color="#4CAF50",
            alpha=0.9, label="干净码片")
    ax.plot(range(show_chips), chips_noisy[:show_chips], linewidth=0.5, color="#9E9E9E",
            alpha=0.7, label="经信道后(SNR=5dB)")
    for i in range(2):
        ax.axvline(x=i*CODE_LENGTH, color="red", linewidth=0.8, linestyle="--", alpha=0.5)
    ax.set_title(f"扩频后码片 (1bit→{CODE_LENGTH}chips, 前2bit)\n绿=发送 灰=经信道收到",
                 fontsize=10, fontweight="bold")
    ax.set_ylim(-3.5, 3.5)
    ax.set_xlabel("码片序号"); ax.set_ylabel("±1")
    ax.legend(fontsize=6, loc="upper right")
    ax.grid(True, alpha=0.3)

    # D) 扩频码互相关
    ax = fig.add_subplot(gs[1, 0])
    cross = np.correlate(our_code, rival_code, mode='same')
    ax.plot(cross, linewidth=0.8, color="#9C27B0")
    ax.axhline(y=0, color="gray", linewidth=0.5)
    ax.set_title(f"队伍0 vs 队伍1 码互相关\n(峰值={np.max(np.abs(cross)):.0f}, 理想=0)",
                 fontsize=11, fontweight="bold")
    ax.set_xlabel("偏移"); ax.set_ylabel("相关值")
    ax.grid(True, alpha=0.3)

    # E) 己方解扩 (加噪后)
    ax = fig.add_subplot(gs[1, 1])
    soft = despread(chips_noisy, our_code, output_bits=False)
    colors = ["#4CAF50" if b == 0 else "#F44336" for b in demo_bits]
    ax.bar(range(len(soft)), soft, color=colors, edgecolor="black", linewidth=0.5)
    ax.axhline(y=0, color="gray", linewidth=1)
    ax.set_title(f"己方解扩软值 (SNR=5dB 正=bit0 负=bit1)\n处理增益 → 信号仍清晰可辨",
                 fontsize=10, fontweight="bold")
    ax.set_xlabel("比特序号"); ax.set_ylabel("相关值")
    ax.grid(True, alpha=0.3)

    # F) 对手解扩 (加噪后)
    ax = fig.add_subplot(gs[1, 2])
    rival_soft = despread(chips_noisy, rival_code, output_bits=False)
    ax.bar(range(len(rival_soft)), rival_soft, color="#9E9E9E", edgecolor="black", linewidth=0.5)
    ax.axhline(y=0, color="gray", linewidth=1)
    ax.set_title(f"对手解扩软值 (SNR=5dB 不知道码→随机)\n处理增益={processing_gain_db(CODE_LENGTH):.1f}dB也帮不了对手",
                 fontsize=10, fontweight="bold")
    ax.set_xlabel("比特序号"); ax.set_ylabel("相关值")
    ax.grid(True, alpha=0.3)

    # G) 己方频谱
    ax = fig.add_subplot(gs[2, 0])
    fft = np.fft.fftshift(np.fft.fft(chips, 4096))
    psd = 20 * np.log10(np.abs(fft) + 1e-12)
    freq = np.fft.fftshift(np.fft.fftfreq(4096))
    ax.plot(freq, psd, linewidth=0.8, color="#2196F3")
    ax.set_title("扩频信号频谱 (类白噪声)", fontsize=11, fontweight="bold")
    ax.set_xlabel("归一化频率"); ax.set_ylabel("PSD (dB)")
    ax.grid(True, alpha=0.3)

    # H) 解扩后星座 (加噪等效 BPSK)
    ax = fig.add_subplot(gs[2, 1])
    pg = processing_gain_db(CODE_LENGTH)
    # 添加少量垂直抖动，让重叠的点可见
    jitter_y = RNG.standard_normal(len(soft)) * 5
    ax.scatter(soft, jitter_y, c=colors, s=60, edgecolors="black",
              linewidth=0.5, zorder=5, alpha=0.85)
    ax.axvline(x=0, color="gray", linewidth=0.5, linestyle="--")
    ax.set_title(f"解扩后等效星座图 (SNR=5dB)\n处理增益 {pg:.1f}dB → 点群仍清晰分离",
                 fontsize=10, fontweight="bold")
    ax.set_xlabel("I (同相分量)"); ax.set_ylabel("Q (正交分量)")
    ax.grid(True, alpha=0.3)

    # I) BER vs SNR 曲线
    ax = fig.add_subplot(gs[2, 2])
    result = evaluate_dsss_performance(
        n_bits=1000, code_length=CODE_LENGTH,
        snr_db_range=[-20, -15, -10, -5, 0, 5, 10], seed=42,
    )
    ax.semilogy(result["snr_db"], result["our_ber"], "o-", color="#4CAF50",
                linewidth=2, markersize=6, label=f"己方DSSS (PG={result['processing_gain_db']:.0f}dB)")
    ax.semilogy(result["snr_db"], result["rival_ber"], "s--", color="#F44336",
                linewidth=2, markersize=6, label="对手(错误码)")
    ax.semilogy(result["snr_db"], result["bpsk_baseline_ber"], "d:", color="#2196F3",
                linewidth=2, markersize=6, label="无扩频BPSK")
    ax.set_title("BER vs SNR 对比", fontsize=11, fontweight="bold")
    ax.set_xlabel("SNR (dB)"); ax.set_ylabel("BER")
    ax.legend(fontsize=7); ax.grid(True, alpha=0.3, which="both")
    ax.set_ylim(1e-4, 1)

    fig.suptitle(
        f"DSSS 直接序列扩频 — 码长={CODE_LENGTH} 处理增益={processing_gain_db(CODE_LENGTH):.1f}dB",
        fontsize=14, fontweight="bold", y=0.99,
    )
    return fig


def plot_multiteam_scenario():
    """图2：多队同时发射时的对抗场景。"""
    fig, axes = plt.subplots(2, 2, figsize=(14, 8))

    # A) 多队扩频码对比
    ax = axes[0, 0]
    code_mgr = SpreadingCodeManager(our_team_id=0, code_length=255)
    for tid, color in [(0, "#4CAF50"), (1, "#F44336"), (2, "#2196F3"), (3, "#FF9800")]:
        c = code_mgr.get_rival_code(tid) if tid > 0 else code_mgr.our_code
        ax.step(range(50), c[:50] + tid * 0.1, where="mid", linewidth=0.8,
                color=color, alpha=0.8, label=f"队伍{tid}")
    ax.set_title("四队扩频码对比 (前50位)", fontsize=11, fontweight="bold")
    ax.set_xlabel("码片"); ax.set_ylabel("±1 (+偏移)")
    ax.legend(fontsize=7); ax.grid(True, alpha=0.3)

    # B) 互相关矩阵
    ax = axes[0, 1]
    teams = [0, 1, 2, 3]
    matrix = np.zeros((4, 4))
    for i, ti in enumerate(teams):
        ci = code_mgr.get_rival_code(ti) if ti > 0 else code_mgr.our_code
        for j, tj in enumerate(teams):
            cj = code_mgr.get_rival_code(tj) if tj > 0 else code_mgr.our_code
            matrix[i, j] = np.abs(np.dot(ci, cj)) / len(ci)
    im = ax.imshow(matrix, cmap="RdYlGn_r", vmin=0, vmax=0.15)
    for i in range(4):
        for j in range(4):
            ax.text(j, i, f"{matrix[i,j]:.3f}", ha="center", va="center",
                    fontsize=9, fontweight="bold")
    ax.set_title("队伍间码互相关矩阵\n(0=完全正交, 1=相同)", fontsize=11, fontweight="bold")
    ax.set_xticks(range(4)); ax.set_yticks(range(4))
    ax.set_xticklabels([f"队{t}" for t in teams])
    ax.set_yticklabels([f"队{t}" for t in teams])
    plt.colorbar(im, ax=ax, shrink=0.8)

    # C) 多队干扰下的己方BER
    ax = axes[1, 0]
    sir_range = [-20, -15, -10, -5, 0, 5, 10]
    bers = []
    for sir in sir_range:
        r = evaluate_multiteam_interference(
            n_bits=2000, code_length=255, snr_db=5.0,
            sir_db=sir, rival_team_ids=[1, 2, 3], seed=42,
        )
        bers.append(r["our_ber"])
    ax.semilogy(sir_range, bers, "o-", color="#4CAF50", linewidth=2, markersize=8)
    ax.axhline(y=0.01, color="red", linewidth=1, linestyle="--", alpha=0.5, label="1% BER")
    ax.set_title("3个对手同时发射时的己方BER\n(SNR=5dB 码长=255)", fontsize=11, fontweight="bold")
    ax.set_xlabel("信干比 SIR (dB) — 越负对手越强")
    ax.set_ylabel("己方 BER")
    ax.legend(fontsize=7); ax.grid(True, alpha=0.3, which="both")

    # D) 策略时间线
    ax = axes[1, 1]
    ctrl = AdversarialController(team_id=0, min_code_length=63, max_code_length=1023)
    scenarios = [
        (20, False, 0, 2000, 1000),   # 好信道
        (18, False, 0, 1800, 1000),
        (3, True, 2, 200, 1000),       # 检测到干扰!
        (1, True, 3, 100, 1000),
        (-2, True, 3, 50, 1000),
        (15, False, 1, 500, 1000),      # 信道恢复
        (18, False, 0, 1500, 1000),
    ]
    code_lens = []
    levels = []
    for snr, intr, rivals, goodput, target in scenarios:
        s = ctrl.select_strategy(snr, intr, rivals, goodput, target)
        code_lens.append(s.code_length)
        levels.append(s.level.value)

    colors_map = {"defensive": "#4CAF50", "spectrum_fill": "#FF9800",
                  "adaptive_length": "#F44336", "code_hopping": "#9C27B0"}
    ax2 = ax.twinx()
    for i, (cl, lv) in enumerate(zip(code_lens, levels)):
        ax.bar(i, cl, color=colors_map.get(lv, "#999"), edgecolor="black", linewidth=0.5)
    ax.set_title("对抗策略动态调整示例", fontsize=11, fontweight="bold")
    ax.set_xlabel("时间步"); ax.set_ylabel("码长")
    ax.set_xticks(range(len(scenarios)))
    ax.set_xticklabels(["好","好","干扰!","干扰!","干扰!","恢复","好"], fontsize=7)
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor=v, label=k) for k, v in colors_map.items()]
    ax.legend(handles=legend_elements, fontsize=7, loc="upper left")
    ax.grid(True, alpha=0.3, axis="y")

    fig.suptitle("多队对抗场景分析", fontsize=13, fontweight="bold")
    fig.subplots_adjust(hspace=0.35, wspace=0.3)
    return fig


def export_all(output_dir: str = "artifacts/plots"):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    matplotlib.use("Agg")

    for name, func in [
        ("adversarial_01_dsss_principle", plot_dsss_principle),
        ("adversarial_02_multiteam", plot_multiteam_scenario),
    ]:
        fig = func()
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            fig.tight_layout()
        path = out / f"{name}.png"
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"  [OK] {path}")

    print(f"\nAll adversarial charts exported to {out}/")


def run_demo():
    print("=" * 60)
    print("  DSSS对抗通信可视化演示")
    print(f"  扩频码长: {CODE_LENGTH}")
    print(f"  处理增益: {processing_gain_db(CODE_LENGTH):.1f} dB")
    print("=" * 60)

    # 快速验证
    wave = AdversarialWaveform(team_id=0, code_length=CODE_LENGTH)
    bits = np.array([0,1,0,1]*10, dtype=np.uint8)
    chips = wave.modulate(bits)
    recovered = wave.demodulate(chips)
    errors = np.sum(bits != recovered)
    print(f"\n扩频解扩验证: {len(bits)} bits, 错误={errors}")

    # 验证不同码解扩
    wave2 = AdversarialWaveform(team_id=1, code_length=CODE_LENGTH)
    recovered2 = wave2.demodulate(chips)
    errors2 = np.sum(bits[:len(recovered2)] != recovered2[:len(bits)])
    print(f"对手码解扩: {len(bits)} bits, 错误={errors2} (应接近50%)")

    print("\n-> 显示 图1: DSSS扩频解扩原理...")
    fig1 = plot_dsss_principle()
    plt.show(block=False)

    input("\n按 Enter 显示 图2: 多队对抗场景...")
    plt.close("all")
    fig2 = plot_multiteam_scenario()
    plt.show(block=False)

    input("\n按 Enter 退出...")
    plt.close("all")
    print("演示结束。")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="DSSS对抗通信可视化")
    ap.add_argument("--export", action="store_true", help="导出所有PNG")
    ap.add_argument("--output-dir", type=str, default="artifacts/plots")
    args = ap.parse_args()

    if args.export:
        export_all(args.output_dir)
    else:
        run_demo()
