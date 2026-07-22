#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
无线通信波形可视化演示
======================
面向新手/外行的交互式信号处理展示。
展示：原始比特 → BPSK调制 → 脉冲成形 → AWGN/干扰 → 匹配滤波 → 星座图

用法：python scripts/demo_waveform.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import numpy as np
import matplotlib
matplotlib.use("TkAgg")  # 交互窗口
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import matplotlib.animation as animation

from wireless_competition.tx.modulation import bytes_to_bits, bpsk_modulate, bpsk_demodulate_hard
from wireless_competition.tx.pulse_shaping import pulse_shape, matched_filter, rrc_filter
from wireless_competition.tx.framing import make_preamble, make_sync_word
from wireless_competition.channel.awgn import add_awgn
from wireless_competition.channel.interference import tone_interference, generate_interference

# ── 中文字体 ──────────────────────────────────────────────────
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# ── 全局参数 ──────────────────────────────────────────────────
SPS = 8                     # 每符号采样数
ROLLOFF = 0.35              # RRC 滚降因子
SPAN = 6                    # RRC 跨度
SYMBOL_COUNT = 40           # 展示符号数
SNR_DB = 5.0                # 信噪比（降低以使噪声可见）
INTERFERENCE_ENABLED = True # 是否添加干扰
RNG = np.random.default_rng(42)


def generate_demo_data():
    """生成演示用信号。"""
    # 固定图案比特（方便观察规律）：交替 + 特定序列
    pattern_bits = np.array(
        [0,0,0,0, 1,1,1,1, 0,1,0,1, 1,0,1,0] * 2
        + [0,0,1,1,0,0,1,1],
        dtype=np.uint8,
    )[:SYMBOL_COUNT]

    symbols = bpsk_modulate(pattern_bits)  # BPSK: +1 / -1

    # 脉冲成形
    shaped_iq = pulse_shape(symbols, SPS, ROLLOFF, SPAN)

    # RRC 滤波器
    rrc_coeff = rrc_filter(SPS, ROLLOFF, SPAN)

    # AWGN
    noisy_iq = add_awgn(shaped_iq, SNR_DB, rng=RNG)

    # 匹配滤波
    mf_iq = matched_filter(noisy_iq, SPS, ROLLOFF, SPAN)

    # 干扰信号 (单音)
    tone_freq = 0.05  # 归一化频率
    interference = tone_interference(
        len(shaped_iq), tone_freq, 1.0, amplitude=0.5
    )

    noisy_interfered = noisy_iq + interference

    # 匹配滤波 (含干扰)
    mf_interfered = matched_filter(noisy_interfered, SPS, ROLLOFF, SPAN)

    # 下采样恢复符号
    def downsample_sym(iq, sps=SPS):
        n_sym = len(iq) // sps
        return iq[:n_sym * sps].reshape(-1, sps).mean(axis=0)[0]  # 取最佳采样点

    # 简单下采样
    sym_clean = shaped_iq[SPS//2::SPS][:SYMBOL_COUNT]
    sym_noisy = mf_iq[SPS//2::SPS][:SYMBOL_COUNT]
    sym_interfered = mf_interfered[SPS//2::SPS][:SYMBOL_COUNT]

    # 硬判决恢复
    rx_bits_clean = bpsk_demodulate_hard(sym_clean)
    rx_bits_noisy = bpsk_demodulate_hard(sym_noisy)
    rx_bits_interfered = bpsk_demodulate_hard(sym_interfered)

    return {
        "bits": pattern_bits,
        "symbols": symbols,
        "shaped_iq": shaped_iq,
        "rrc_coeff": rrc_coeff,
        "noisy_iq": noisy_iq,
        "mf_iq": mf_iq,
        "interference": interference,
        "noisy_interfered": noisy_interfered,
        "mf_interfered": mf_interfered,
        "sym_clean": sym_clean,
        "sym_noisy": sym_noisy,
        "sym_interfered": sym_interfered,
        "rx_bits_clean": rx_bits_clean,
        "rx_bits_noisy": rx_bits_noisy,
        "rx_bits_interfered": rx_bits_interfered,
    }


def plot_main_figure(data):
    """主图：6 面板全面展示。"""
    fig = plt.figure(figsize=(16, 10))
    gs = GridSpec(3, 3, figure=fig, hspace=0.45, wspace=0.35)

    t = np.arange(len(data["shaped_iq"])) / SPS  # 符号时间轴
    t_sym = np.arange(SYMBOL_COUNT)

    # ── 面板 1：发射端 ──────────────────────────────────────────
    # A) 原始比特
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.step(t_sym, data["bits"], where="mid", linewidth=1.5, color="#2196F3")
    ax1.set_title("① 原始发送比特 (0/1)", fontsize=11, fontweight="bold")
    ax1.set_xlabel("比特序号")
    ax1.set_ylabel("比特值")
    ax1.set_ylim(-0.2, 1.2)
    ax1.set_yticks([0, 1])
    ax1.grid(True, alpha=0.3)

    # B) BPSK 星座图 (干净)
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.scatter(np.real(data["symbols"]), np.imag(data["symbols"]),
               c=["#4CAF50" if b == 0 else "#F44336" for b in data["bits"]],
               s=60, edgecolors="black", linewidth=0.5, zorder=5)
    ax2.axhline(y=0, color="gray", linewidth=0.5, linestyle="--")
    ax2.axvline(x=0, color="gray", linewidth=0.5, linestyle="--")
    ax2.set_xlim(-1.5, 1.5)
    ax2.set_ylim(-1.5, 1.5)
    ax2.set_title("② BPSK 星座图 (0→+1, 1→-1)", fontsize=11, fontweight="bold")
    ax2.set_xlabel("同相分量 I")
    ax2.set_ylabel("正交分量 Q")
    ax2.set_aspect("equal")
    ax2.grid(True, alpha=0.3)
    # 图例
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#4CAF50",
               markersize=8, label="比特 0 → +1"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#F44336",
               markersize=8, label="比特 1 → -1"),
    ]
    ax2.legend(handles=legend_elements, fontsize=8, loc="lower right")

    # C) RRC 滤波器形状
    ax3 = fig.add_subplot(gs[0, 2])
    rrc_t = np.arange(len(data["rrc_coeff"])) / SPS - SPAN
    ax3.plot(rrc_t, data["rrc_coeff"], color="#FF9800", linewidth=1.5)
    ax3.fill_between(rrc_t, 0, data["rrc_coeff"], alpha=0.2, color="#FF9800")
    ax3.set_title("③ RRC 脉冲成形滤波器", fontsize=11, fontweight="bold")
    ax3.set_xlabel("时间 (符号周期)")
    ax3.set_ylabel("幅度")
    ax3.grid(True, alpha=0.3)
    ax3.axhline(y=0, color="gray", linewidth=0.5)

    # ── 面板 2：信号波形 ────────────────────────────────────────
    # D) 脉冲成形后的发送信号
    ax4 = fig.add_subplot(gs[1, 0])
    ax4.plot(t, np.real(data["shaped_iq"]), linewidth=0.8, color="#2196F3", alpha=0.9)
    ax4.set_title("④ 脉冲成形后的发送波形 (I路)", fontsize=11, fontweight="bold")
    ax4.set_xlabel("时间 (符号周期)")
    ax4.set_ylabel("幅度")
    ax4.grid(True, alpha=0.3)
    ax4.set_xlim(0, t[-1])

    # E) 噪声 + 干扰后的信号
    ax5 = fig.add_subplot(gs[1, 1])
    ax5.plot(t, np.real(data["noisy_iq"]), linewidth=0.6, color="#9E9E9E",
             alpha=0.7, label="含噪声信号")
    ax5.plot(t, np.real(data["interference"]), linewidth=0.8, color="#F44336",
             alpha=0.8, label="单音干扰")
    ax5.set_title("⑤ 含噪声 + 单音干扰的波形", fontsize=11, fontweight="bold")
    ax5.set_xlabel("时间 (符号周期)")
    ax5.set_ylabel("幅度")
    ax5.legend(fontsize=7, loc="upper right")
    ax5.grid(True, alpha=0.3)
    ax5.set_xlim(0, t[-1])

    # F) 匹配滤波后的信号
    ax6 = fig.add_subplot(gs[1, 2])
    ax6.plot(t[:len(data["mf_iq"])], np.real(data["mf_iq"]),
             linewidth=0.8, color="#4CAF50", alpha=0.8, label="仅噪声")
    ax6.plot(t[:len(data["mf_interfered"])], np.real(data["mf_interfered"]),
             linewidth=0.8, color="#FF9800", alpha=0.8, label="噪声+干扰")
    ax6.set_title("⑥ 匹配滤波后 (恢复符号)", fontsize=11, fontweight="bold")
    ax6.set_xlabel("时间 (符号周期)")
    ax6.set_ylabel("幅度")
    ax6.legend(fontsize=7, loc="upper right")
    ax6.grid(True, alpha=0.3)

    # ── 面板 3：星座图对比 ─────────────────────────────────────
    # G) 接收星座图 (仅噪声)
    ax7 = fig.add_subplot(gs[2, 0])
    ax7.scatter(np.real(data["sym_noisy"]), np.imag(data["sym_noisy"]),
               c=["#4CAF50" if b == 0 else "#F44336" for b in data["rx_bits_noisy"]],
               s=50, edgecolors="black", linewidth=0.5, zorder=5, alpha=0.8)
    ax7.axhline(y=0, color="gray", linewidth=0.5, linestyle="--")
    ax7.axvline(x=0, color="gray", linewidth=0.5, linestyle="--")
    ax7.set_xlim(-2, 2)
    ax7.set_ylim(-2, 2)
    ax7.set_title(f"⑦ 接收星座图 (SNR={SNR_DB}dB)", fontsize=11, fontweight="bold")
    ax7.set_xlabel("同相分量 I")
    ax7.set_ylabel("正交分量 Q")
    ax7.set_aspect("equal")
    ax7.grid(True, alpha=0.3)

    # H) 接收星座图 (噪声+干扰)
    ax8 = fig.add_subplot(gs[2, 1])
    ax8.scatter(np.real(data["sym_interfered"]), np.imag(data["sym_interfered"]),
               c=["#4CAF50" if b == 0 else "#F44336" for b in data["rx_bits_interfered"]],
               s=50, edgecolors="black", linewidth=0.5, zorder=5, alpha=0.8)
    ax8.axhline(y=0, color="gray", linewidth=0.5, linestyle="--")
    ax8.axvline(x=0, color="gray", linewidth=0.5, linestyle="--")
    ax8.set_xlim(-2, 2)
    ax8.set_ylim(-2, 2)
    ax8.set_title(f"⑧ 含干扰接收星座图", fontsize=11, fontweight="bold")
    ax8.set_xlabel("同相分量 I")
    ax8.set_ylabel("正交分量 Q")
    ax8.set_aspect("equal")
    ax8.grid(True, alpha=0.3)

    # I) 比特对比
    ax9 = fig.add_subplot(gs[2, 2])
    ax9.step(t_sym, data["bits"], where="mid", linewidth=2, color="#2196F3",
             label="发送比特")
    ax9.step(t_sym + 0.1, data["rx_bits_noisy"], where="mid", linewidth=1.5,
             color="#4CAF50", alpha=0.8, label="恢复(仅噪声)")
    ax9.step(t_sym + 0.2, data["rx_bits_interfered"], where="mid", linewidth=1.5,
             color="#FF9800", alpha=0.8, label="恢复(噪声+干扰)")
    ax9.set_title("⑨ 发送/接收比特对比", fontsize=11, fontweight="bold")
    ax9.set_xlabel("比特序号")
    ax9.set_ylabel("比特值")
    ax9.set_ylim(-0.3, 1.3)
    ax9.set_yticks([0, 1])
    ax9.legend(fontsize=7, loc="upper right")
    ax9.grid(True, alpha=0.3)

    # 统计
    errors_noisy = int(np.sum(data["bits"] != data["rx_bits_noisy"][:SYMBOL_COUNT]))
    errors_interf = int(np.sum(data["bits"] != data["rx_bits_interfered"][:SYMBOL_COUNT]))
    ber_noisy = errors_noisy / SYMBOL_COUNT
    ber_interf = errors_interf / SYMBOL_COUNT

    fig.suptitle(
        f"无线通信信号处理全流程演示 | SNR={SNR_DB}dB | "
        f"仅噪声BER={ber_noisy:.3f} | 含干扰BER={ber_interf:.3f} | "
        f"绿=比特0(+1) 红=比特1(-1)",
        fontsize=13, fontweight="bold", y=0.99
    )

    return fig


def plot_spectrum(data):
    """频谱图：展示信号的频率分布。"""
    fig, axes = plt.subplots(2, 2, figsize=(14, 8))

    # PSD 函数
    def compute_psd(sig):
        n = len(sig)
        fft = np.fft.fftshift(np.fft.fft(sig))
        psd = 10 * np.log10(np.abs(fft) ** 2 + 1e-12)
        freq = np.fft.fftshift(np.fft.fftfreq(n, 1/SPS))
        return freq, psd

    titles = [
        ("发送信号频谱", "shaped_iq", "#2196F3"),
        ("含噪声信号频谱", "noisy_iq", "#9E9E9E"),
        ("干扰信号频谱", "interference", "#F44336"),
        ("匹配滤波后频谱", "mf_interfered", "#FF9800"),
    ]

    for ax, (title, key, color) in zip(axes.flat, titles):
        freq, psd = compute_psd(data[key])
        ax.plot(freq, psd, linewidth=0.8, color=color)
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.set_xlabel("归一化频率")
        ax.set_ylabel("功率谱密度 (dB)")
        ax.grid(True, alpha=0.3)

    fig.suptitle("频域分析 — 功率谱密度 (PSD)", fontsize=13, fontweight="bold")
    fig.subplots_adjust(hspace=0.35, wspace=0.3)
    return fig


def plot_filter_comparison(data):
    """滤波器前后对比详解。"""
    fig, axes = plt.subplots(2, 2, figsize=(14, 8))
    t = np.arange(len(data["shaped_iq"])) / SPS

    # 1. 原始发送信号 vs 加噪后
    ax = axes[0, 0]
    ax.plot(t, np.real(data["shaped_iq"]), linewidth=1, color="#2196F3",
            alpha=0.9, label="原始发送信号")
    ax.plot(t, np.real(data["noisy_iq"]), linewidth=0.6, color="#9E9E9E",
            alpha=0.7, label=f"加噪后 (SNR={SNR_DB}dB)")
    ax.set_title("噪声对信号的影响", fontsize=11, fontweight="bold")
    ax.set_xlabel("时间 (符号周期)")
    ax.set_ylabel("幅度")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, t[-1])

    # 2. RRC 滤波器响应 (时域 + 频域)
    ax = axes[0, 1]
    rrc = data["rrc_coeff"]
    rrc_t = np.arange(len(rrc)) / SPS - SPAN
    ax.plot(rrc_t, rrc, linewidth=1.5, color="#FF9800")
    ax.fill_between(rrc_t, 0, rrc, alpha=0.15, color="#FF9800")
    # 频域响应
    rrc_pad = np.zeros(1024)
    rrc_pad[:len(rrc)] = rrc
    rrc_freq = np.fft.fftshift(np.fft.fftfreq(1024, 1/SPS))
    rrc_fft = 20 * np.log10(np.abs(np.fft.fftshift(np.fft.fft(rrc_pad))) + 1e-12)
    ax2 = ax.twinx()
    ax2.plot(rrc_freq, rrc_fft, linewidth=1, color="#9C27B0", alpha=0.6,
             linestyle="--")
    ax2.set_ylabel("频率响应 (dB)", color="#9C27B0")
    ax.set_title("RRC 滤波器 (时域+频域)", fontsize=11, fontweight="bold")
    ax.set_xlabel("时间/频率")
    ax.set_ylabel("时域幅度")
    ax.grid(True, alpha=0.3)

    # 3. 匹配滤波前后对比
    ax = axes[1, 0]
    ax.plot(t, np.real(data["noisy_iq"]), linewidth=0.6, color="#9E9E9E",
            alpha=0.5, label="滤波前 (含噪声)")
    ax.plot(t[:len(data["mf_iq"])], np.real(data["mf_iq"]), linewidth=1,
            color="#4CAF50", alpha=0.9, label="滤波后 (匹配滤波)")
    ax.set_title("匹配滤波 — 降噪效果", fontsize=11, fontweight="bold")
    ax.set_xlabel("时间 (符号周期)")
    ax.set_ylabel("幅度")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # 4. 符号采样点 (眼图简化)
    ax = axes[1, 1]
    # 叠加所有符号的波形段
    sym_len = SPS
    n_syms = min(30, len(data["mf_iq"]) // sym_len - 1)
    colors = plt.cm.viridis(np.linspace(0, 1, n_syms))
    for i in range(n_syms):
        seg = np.real(data["mf_iq"][i*sym_len:(i+2)*sym_len])
        ax.plot(np.arange(len(seg)) / SPS, seg, linewidth=0.5, color=colors[i],
                alpha=0.6)
    ax.axvline(x=1, color="red", linewidth=1.5, linestyle="--", alpha=0.7,
              label="最佳采样点")
    ax.set_title("眼图 (匹配滤波后) — 信号张开程度", fontsize=11, fontweight="bold")
    ax.set_xlabel("时间 (符号周期)")
    ax.set_ylabel("幅度")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    fig.suptitle("滤波器工作原理详解", fontsize=13, fontweight="bold")
    return fig


def plot_interference_analysis(data):
    """干扰分析与滤波效果。"""
    fig, axes = plt.subplots(2, 2, figsize=(14, 8))
    t = np.arange(len(data["shaped_iq"])) / SPS

    # 1. 干扰信号波形
    ax = axes[0, 0]
    ax.plot(t[:200], np.real(data["interference"][:200]), linewidth=1.2,
            color="#F44336")
    ax.set_title("单音干扰 (正弦波)", fontsize=11, fontweight="bold")
    ax.set_xlabel("时间 (符号周期)")
    ax.set_ylabel("幅度")
    ax.grid(True, alpha=0.3)

    # 2. 信号 + 干扰 = 混合信号
    ax = axes[0, 1]
    ax.plot(t[:200], np.real(data["shaped_iq"][:200]), linewidth=1,
            color="#2196F3", alpha=0.7, label="原始信号")
    ax.plot(t[:200], np.real(data["interference"][:200]), linewidth=0.8,
            color="#F44336", alpha=0.7, label="干扰")
    ax.plot(t[:200], np.real(data["noisy_interfered"][:200]), linewidth=0.8,
            color="#FF9800", alpha=0.9, label="信号+干扰")
    ax.set_title("干扰如何叠加到信号上", fontsize=11, fontweight="bold")
    ax.set_xlabel("时间 (符号周期)")
    ax.set_ylabel("幅度")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)

    # 3. 匹配滤波对抗干扰
    ax = axes[1, 0]
    ax.plot(t[:len(data["mf_iq"])], np.real(data["mf_iq"]), linewidth=0.8,
            color="#4CAF50", alpha=0.8, label="仅噪声→滤波后")
    ax.plot(t[:len(data["mf_interfered"])], np.real(data["mf_interfered"]),
            linewidth=0.8, color="#FF9800", alpha=0.8, label="噪声+干扰→滤波后")
    ax.set_title("匹配滤波器的抗干扰效果", fontsize=11, fontweight="bold")
    ax.set_xlabel("时间 (符号周期)")
    ax.set_ylabel("幅度")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # 4. 误码统计柱状图
    ax = axes[1, 1]
    errors_noisy = int(np.sum(data["bits"] != data["rx_bits_noisy"][:SYMBOL_COUNT]))
    errors_interf = int(np.sum(data["bits"] != data["rx_bits_interfered"][:SYMBOL_COUNT]))
    bars = ax.bar(
        ["仅 AWGN 噪声", "噪声 + 单音干扰"],
        [errors_noisy, errors_interf],
        color=["#4CAF50", "#F44336"],
        edgecolor="black",
        linewidth=1,
    )
    for bar, val in zip(bars, [errors_noisy, errors_interf]):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
                f"{val}/{SYMBOL_COUNT}\nBER={val/SYMBOL_COUNT:.3f}",
                ha="center", fontsize=10, fontweight="bold")
    ax.set_title("误码统计对比", fontsize=11, fontweight="bold")
    ax.set_ylabel("错误比特数")
    ax.set_ylim(0, max(errors_noisy, errors_interf) * 1.5 + 1)

    fig.suptitle(
        f"干扰分析 — SNR={SNR_DB}dB 单音干扰",
        fontsize=13, fontweight="bold"
    )
    fig.subplots_adjust(hspace=0.35, wspace=0.3)
    return fig


def run_demo():
    """运行交互式演示。"""
    print("=" * 60)
    print("  无线通信波形可视化演示")
    print("  BPSK 调制 → RRC 脉冲成形 → AWGN + 干扰 → 匹配滤波")
    print("=" * 60)
    print()
    print("正在生成演示数据...")

    data = generate_demo_data()

    # 统计
    errors_noisy = int(np.sum(data["bits"] != data["rx_bits_noisy"][:SYMBOL_COUNT]))
    errors_interf = int(np.sum(data["bits"] != data["rx_bits_interfered"][:SYMBOL_COUNT]))
    print(f"  符号数: {SYMBOL_COUNT}")
    print(f"  SNR: {SNR_DB} dB")
    print(f"  仅噪声误码: {errors_noisy}/{SYMBOL_COUNT} (BER={errors_noisy/SYMBOL_COUNT:.4f})")
    print(f"  含干扰误码: {errors_interf}/{SYMBOL_COUNT} (BER={errors_interf/SYMBOL_COUNT:.4f})")
    print()

    # 图 1：主全景图
    print("→ 显示 图1: 信号处理全流程...")
    fig1 = plot_main_figure(data)
    fig1.tight_layout()
    plt.show(block=False)

    # 图 2：频域分析
    input("\n按 Enter 显示 图2: 频域分析...")
    plt.close("all")
    fig2 = plot_spectrum(data)
    plt.show(block=False)

    # 图 3：滤波器详解
    input("\n按 Enter 显示 图3: 滤波器工作原理...")
    plt.close("all")
    fig3 = plot_filter_comparison(data)
    plt.show(block=False)

    # 图 4：干扰分析
    input("\n按 Enter 显示 图4: 干扰分析与误码统计...")
    plt.close("all")
    fig4 = plot_interference_analysis(data)
    plt.show(block=False)

    input("\n按 Enter 退出...")
    plt.close("all")
    print("演示结束。")


# ── 一键导出 PNG ─────────────────────────────────────────────
def export_all_pngs(output_dir: str = "artifacts/plots"):
    """非交互模式：导出所有图为 PNG。"""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    data = generate_demo_data()
    matplotlib.use("Agg")  # 无 GUI 后端

    for name, func in [
        ("01_full_pipeline", plot_main_figure),
        ("02_spectrum", plot_spectrum),
        ("03_filter_detail", plot_filter_comparison),
        ("04_interference_analysis", plot_interference_analysis),
    ]:
        fig = func(data)
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            fig.tight_layout()
        path = out / f"{name}.png"
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"  [OK] {path}")

    print(f"\nAll charts exported to {out}/")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="无线通信波形可视化演示")
    ap.add_argument("--export", action="store_true",
                    help="非交互模式：导出所有PNG图片")
    ap.add_argument("--output-dir", type=str, default="artifacts/plots",
                    help="PNG输出目录")
    args = ap.parse_args()

    if args.export:
        matplotlib.use("Agg")
        export_all_pngs(args.output_dir)
    else:
        run_demo()
