# ⚡ 电波对决争锋 — 无线通信竞赛备赛系统 完整手册

> **项目定位**：基于 SDR 的混合式智能通信系统 — 传统通信保证可用，机器学习识别环境，DSSS 扩频对抗压制。
> **测试**：163/163 全部通过 | **语言**：Python 3.11+ | **核心依赖**：NumPy/SciPy/scikit-learn

---

## 0. 五分钟速览

```
你的文件 ──→ [TX: 分块→编码→调制→脉冲成形] ──→ [虚拟信道: 噪声+干扰]
                                                         │
你的文件 ←── [RX: 解调→译码→CRC→重组] ←── [匹配滤波+同步+检测]
```

**一句话**：把任意二进制文件通过模拟无线电信道发出去再收回来。噪声越大、干扰越强，DSSS 扩频的优势越明显。

---

## 1. 快速开始

### 1.1 安装

```bash
cd "C:\Users\16839\Desktop\无线电 - 副本"
pip install -e .
```

### 1.2 跑通验证

```bash
# 全部测试 (163项)
python -m pytest tests/unit/ tests/integration/ tests/operation/ tests/regression/ src/wireless_competition/adversarial/tests/ -v

# 端到端仿真
python -m wireless_competition.cli.simulate --data-size 1024 --snr-db 10 --modulation bpsk

# 可视化演示
python scripts/demo_waveform.py --export
python scripts/demo_adversarial.py --export
python scripts/demo_ml.py --export
```

---

## 2. 项目结构地图

```
📁 项目根目录
├── 📄 README.md          ← 你正在看
├── 📄 PLAN.md            ← 完整备赛计划（2200行工程总纲）
├── 📄 SIMULATION.md      ← 模拟程序架构+有效性论证+域迁移
├── 📄 STATUS.md          ← 当前进度+测试统计
├── 📄 DECISIONS.md       ← 架构决策记录(ADR)
│
├── 📁 configs/           ← 配置文件（调参改这里）
├── 📁 src/wireless_competition/
│   ├── common/           ← 🔧 公共工具：类型/配置/种子/日志/缓冲/恢复
│   ├── tx/               ← 🔴 发送端：调制/FEC/脉冲/组帧/OFDM
│   ├── rx/               ← 🟢 接收端：检测/同步/解调/译码/均衡
│   ├── channel/          ← 🟡 信道：AWGN/损伤/干扰/多径
│   ├── file_protocol/    ← 📦 文件：切块/帧头/CRC/重组
│   ├── adversarial/      ← ⚔️ DSSS对抗：扩频/策略/评估/帧
│   ├── ml/               ← 🤖 机器学习：数据集/随机森林
│   ├── features/         ← 📐 特征提取：时域+频域+接收机
│   ├── evaluation/       ← 📊 评估：指标/MonteCarlo/多队模拟
│   ├── policy/           ← 🎯 策略：自适应联动
│   ├── sdr/              ← 📡 SDR：抽象接口+仿真器
│   └── cli/              ← 🖥 命令行：simulate/transmit/receive/train/evaluate
│
├── 📁 scripts/           ← 一键脚本：demo/冒烟测试
├── 📁 tests/             ← 自动测试 (unit/integration/regression)
└── 📁 artifacts/plots/   ← 可视化图表输出
```

---

## 3. 发送端 (TX) — 把文件变成电波

### 3.1 核心模块

| 步骤 | 模块 | 做了什么 |
|---|---|---|
| 1 | `file_protocol/chunker.py` | 大文件切成 256 字节块 |
| 2 | `file_protocol/frame_header.py` | 每块加 14 字节帧头（序号/文件ID/长度/CRC） |
| 3 | `file_protocol/integrity.py` | 载荷加 CRC-32 校验 |
| 4 | `tx/fec.py` | 卷积码纠错 (rate 1/2, K=7, NASA-DSN) |
| 5 | `tx/interleaver.py` | 块交织打散比特（抗突发错误） |
| 6 | `tx/modulation.py` | BPSK (0→+1, 1→-1) 或 QPSK |
| 7 | `tx/pulse_shaping.py` | RRC 脉冲成形（把方波磨圆） |
| 8 | `tx/framing.py` | 组装帧：[Guard][Preamble][Sync][Header][Pilot][Payload+CRC][Guard] |

### 3.2 最简代码

```python
from wireless_competition.tx.pipeline import TXPipeline
from wireless_competition.common.types import ModulationType, FECType

tx = TXPipeline(
    modulation=ModulationType.BPSK,   # BPSK 或 QPSK
    fec_type=FECType.CONVOLUTIONAL,  # 卷积码纠错
    block_size=256,                  # 每块字节数
    seed=42,
)

data = open("要发的文件.bin", "rb").read()
frames = tx.process_file(data)       # list of IQ waveforms
all_iq = tx.concat_frames(frames)    # 拼接成连续信号
```

### 3.3 OFDM 发送端

```python
from wireless_competition.tx.ofdm import OFDMModem

modem = OFDMModem(
    n_subcarriers=64,      # 子载波数
    cp_length=16,          # 循环前缀（抗多径）
    pilot_spacing=8,       # 导频间距
    modulation="bpsk",     # 或 "qpsk"
)

bits = (np.random.random(modem.bits_per_ofdm_symbol * 5) > 0.5).astype(np.uint8)
tx_signal = modem.modulate(bits)     # IFFT + CP
rx_bits = modem.demodulate(tx_signal) # FFT + 导频信道估计 + 均衡
```

---

## 4. 接收端 (RX) — 从噪声中恢复文件

### 4.1 核心模块

| 步骤 | 模块 | 做了什么 |
|---|---|---|
| 1 | `rx/detector.py` | 前导 PN 相关找到帧起始位置 |
| 2 | `rx/cfo.py` | 估计并校正载波频偏 |
| 3 | `rx/timing.py` | Gardner 定时恢复（找最佳采样点） |
| 4 | `rx/carrier.py` | Costas 环跟踪残余相位 |
| 5 | `rx/demodulation.py` | 软/硬解调，LLR 计算 |
| 6 | `rx/decoder.py` | 去交织 + 维特比译码 + CRC 校验 |
| 7 | `rx/equalizer.py` | LMS 自适应均衡（对抗多径） |
| 8 | `file_protocol/assembler.py` | 去重、乱序重组、断点保存 |

### 4.2 最简代码

```python
from wireless_competition.rx.sim_receiver import SimulationReceiver
from wireless_competition.file_protocol.assembler import FileAssembler
from wireless_competition.common.types import RxProfile, ModulationType, FECType

rx = SimulationReceiver(profile=RxProfile(
    modulation=ModulationType.BPSK,
    fec_type=FECType.CONVOLUTIONAL,
))
assembler = FileAssembler()

for frame_iq in received_frames:
    result = rx.process_frame(frame_iq, guard_symbols=16)
    if result.payload_crc_pass:
        assembler.accept_raw(
            file_id=result.metadata.file_id,
            block_seq=result.metadata.block_sequence,
            total_blocks=result.metadata.total_blocks,
            payload=result.payload_bytes,
        )

if assembler.is_complete(0):
    print("文件收全！")
```

---

## 5. 信道模拟 — 仿真空气+对手

### 5.1 12 种损伤

```python
from wireless_competition.channel.pipeline import ChannelPipeline
from wireless_competition.common.types import ChannelConfig

channel = ChannelPipeline(ChannelConfig(
    snr_db=8.0,                    # AWGN 信噪比
    cfo_hz=200.0,                  # 载波频偏
    enable_interference=True,      # 开启干扰
    interference_type="tone",      # 单音/多音/扫频/宽带/带限/突发
    inr_db=5.0,                    # 干扰噪声比
    enable_multipath=True,         # 多径
    channel_taps=[1.0, 0.5+0.3j], # 信道冲激响应
    enable_phase_noise=True,       # 相位噪声
    phase_noise_std_rad=0.01,
    enable_iq_imbalance=True,      # IQ 不平衡
    iq_gain_imbalance_db=1.0,
    enable_clipping=True,          # 削顶
    clipping_threshold=1.0,
    enable_drop_samples=True,      # 丢样 (模拟USB断连)
    drop_probability=0.01,
))

import numpy as np
output = channel.apply(tx_signal, sample_rate_hz=2e6, rng=np.random.default_rng(42))
noisy_signal = output.iq  # 这就是经过"空气"后的信号
```

---

## 6. 对抗通信 (DSSS) — 比赛杀手锏

### 6.1 原理

把 1 个比特展开成 N 个码片。己方知道密码→信号增强 10×log₁₀(N) dB。对手不知道→白噪声。

| 码长 | 处理增益 | 速率 | 场景 |
|---|---|---|---|
| 63 | 18 dB | 1.6% | 好信道 |
| 255 | 24 dB | 0.4% | 日常对抗 |
| 1023 | 30 dB | 0.1% | 强对抗 SNR=-20dB 保底 |

### 6.2 简化链路（含 CRC）

```python
from wireless_competition.adversarial.link import dsss_end_to_end

data = b"hello world" * 50
result = dsss_end_to_end(
    data, team_id=0, code_length=255, snr_db=-10, seed=42
)
print(f"恢复: {result['correct_bytes']}/{result['total_bytes']} 字节")
# → 恢复: 550/550 字节 (SNR=-10dB 仍完美!)
```

### 6.3 完整帧链路

```python
from wireless_competition.adversarial.frame import dsss_frame_end_to_end

data = np.random.default_rng(42).bytes(2000)
result = dsss_frame_end_to_end(
    data, team_id=0, code_length=255, snr_db=-5, block_size=200, seed=42
)
print(f"分{result['total_frames']}块, 恢复{result['correct_bytes']}B, 完整={result['complete']}")
# → 分10块, 恢复2000B, 完整=True
```

---

## 7. 机器学习 — 干扰识别

### 7.1 37 维特征提取

```python
from wireless_competition.features.time_domain import FeatureExtractor

ext = FeatureExtractor(window_samples=1024)
iq = np.random.default_rng(1).standard_normal(1024) + \
     1j * np.random.default_rng(2).standard_normal(1024)
features = ext.extract(iq)  # → (37,) float64 向量
# 含：功率/RMS/PAPR/偏度/峰度/过零率/削顶比/子带功率/
#      谱峰/频谱质心/平坦度/熵/带边比/EVM/SNR/CFO/PER
```

### 7.2 训练与推理

```python
from wireless_competition.ml.dataset import generate_dataset
from wireless_competition.ml.random_forest import InterferenceClassifier

# 生成训练数据
ds = generate_dataset(n_captures_per_class=10, window_samples=512)
train, val, test = ds.split_by_capture(seed=42)

# 训练
clf = InterferenceClassifier(n_estimators=80, max_depth=12)
clf.fit(train)

# 评估
ev = clf.evaluate(test)
print(f"准确率: {ev['accuracy']:.1%},  Macro F1: {ev['macro_f1']:.2f}")

# 单次推理
result = clf.predict(features)
# → {"class": "tone", "confidence": 0.92, "is_ood": False, "reliable": True}
```

---

## 8. 对抗策略控制

```python
from wireless_competition.policy.rule_policy import AdaptiveRXWrapper

wrapper = AdaptiveRXWrapper(team_id=0, min_code_length=63, max_code_length=1023)

# 信道好 → 短码提速
s = wrapper.select_strategy(snr_db=20.0)
print(f"好信道: 码长={s.code_length}, 等级={s.level.value}")
# → 码长=63, 等级=defensive

# 检测到干扰 → 长码对抗
s = wrapper.select_strategy(snr_db=2.0, interference_detected=True, per=0.3)
print(f"干扰: 码长={s.code_length}, 原因={s.reason}")
# → 码长=126, 原因=低SNR增加码长
```

---

## 9. 多队比赛模拟

```python
from wireless_competition.evaluation.contest_sim import simulate_contest

result = simulate_contest(
    n_teams=4,
    data_size=500,
    snr_db=10,
    sir_db=0,                    # 各队功率相同
    dsss_enabled=[True, True, False, False],  # 前两队DSSS，后两队传统
    dsss_code_length=255,
    seed=42,
)

for r in result["team_results"]:
    print(f"队伍{r['team_id']} {'DSSS' if r['dsss_enabled'] else '传统'}: "
          f"BER={r['ber']:.3f}")
```

---

## 10. 命令行工具

### 10.1 端到端仿真

```bash
python -m wireless_competition.cli.simulate \
    --data-size 1024 \
    --snr-db 10 \
    --modulation bpsk \
    --fec convolutional \
    --seed 42
```

### 10.2 生成训练数据集

```bash
python -m wireless_competition.cli.generate_dataset \
    --captures-per-class 15 \
    --windows-per-capture 10 \
    --output data/processed/my_dataset.npz
```

### 10.3 训练分类器

```bash
python -m wireless_competition.cli.train_classifier \
    --n-estimators 80 \
    --max-depth 12 \
    --output artifacts/models/ic_model.joblib
```

### 10.4 Monte Carlo 评估

```bash
python -m wireless_competition.cli.evaluate \
    --n-seeds 20 \
    --snr-db 10 \
    --modulation qpsk \
    --output artifacts/reports/eval.json
```

---

## 11. 可视化演示

### 11.1 传统波形（4 张图）

```bash
python scripts/demo_waveform.py --export
# → artifacts/plots/01_full_pipeline.png  (全流程9面板)
# → artifacts/plots/02_spectrum.png       (频域PSD)
# → artifacts/plots/03_filter_detail.png  (滤波器+眼图)
# → artifacts/plots/04_interference_analysis.png (干扰分析)
```

### 11.2 DSSS 对抗（2 张图）

```bash
python scripts/demo_adversarial.py --export
# → artifacts/plots/adversarial_01_dsss_principle.png (扩频原理)
# → artifacts/plots/adversarial_02_multiteam.png      (多队对抗)
```

### 11.3 ML 分类器（1 张图）

```bash
python scripts/demo_ml.py --export
# → artifacts/plots/ml_01_classifier_report.png (混淆矩阵+特征重要性+F1)
```

---

## 12. 调参速查表

| 场景 | 调制 | FEC | 块大小 | 码长(DSSS) | 说明 |
|---|---|---|---|---|---|
| 极差环境保底 | BPSK | CONVOLUTIONAL | 128 | 1023 | 宁可慢，不能断 |
| 常规稳健 | BPSK | CONVOLUTIONAL | 256 | 255 | 平衡可靠性和速度 |
| 对抗模式 | BPSK | CONVOLUTIONAL | 256 | 255 | DSSS 天然抗干扰 |
| 良好信道冲刺 | QPSK | NONE | 512 | 63 | 最大化吞吐 |
| 窄带干扰 | BPSK | CONVOLUTIONAL | 256 | 255 | 配合陷波滤波器 |
| 突发干扰 | BPSK | CONVOLUTIONAL | 128 | 255 | 配合深交织 |

---

## 13. 核心知识点

### 13.1 通信基础

| 概念 | 通俗解释 | 对应模块 |
|---|---|---|
| BPSK | 相位0°=比特0，相位180°=比特1。只用实数轴两个点 | `tx/modulation.py` |
| QPSK | 4个相位=每符号2比特。速率翻倍但抗噪略差 | `tx/modulation.py` |
| RRC 脉冲成形 | 把方波"磨圆"防止符号间干扰，发端成形+收端匹配=最佳接收 | `tx/pulse_shaping.py` |
| 卷积码 FEC | 加冗余比特，收端维特比译码可纠错 | `tx/fec.py` |
| CRC | 检测数据是否损坏的校验码 | `file_protocol/integrity.py` |
| CFO | 收发本振频率不同步导致的相位旋转 | `rx/cfo.py` |
| 匹配滤波 | 收端用和发端一样的RRC滤波器，最大化信噪比 | `tx/pulse_shaping.py` |
| Costas 环 | 跟踪残余相位旋转的自适应算法 | `rx/carrier.py` |
| OFDM | 把高速数据流分到多个低速子载波，各子载波正交 | `tx/ofdm.py` |

### 13.2 对抗技术

| 概念 | 通俗解释 | 对应模块 |
|---|---|---|
| DSSS 扩频 | 1比特→N个码片，己方密码增强信号，对手看到噪声 | `adversarial/dsss.py` |
| Gold 码 | 具有优良互相关的伪随机序列，不同队伍码互不干扰 | `adversarial/gold_code.py` |
| 处理增益 | 10×log₁₀(码长) dB，码长1023=30dB | `adversarial/dsss.py` |
| OOD 检测 | 干扰类型不在训练集中→回退安全策略 | `ml/random_forest.py` |

### 13.3 工程保障

| 概念 | 对应模块 |
|---|---|
| 可复现性 | `common/seeds.py` — 所有随机操作固定种子 |
| 配置管理 | `common/config.py` — YAML合并+RF安全校验 |
| 环形缓冲 | `common/buffer.py` — 线程安全+丢样监控 |
| 异常恢复 | `common/recovery.py` — 重试→回退+IQ清洗 |

---

## 14. 测试体系

| 层级 | 路径 | 说明 |
|---|---|---|
| 单元 | `tests/unit/` | 每个函数独立测试 |
| 集成 | `tests/integration/` | 模块组合端到端 |
| 回归 | `tests/regression/` | 固定种子确保不退化 |
| 对抗 | `adversarial/tests/` | DSSS 专项 21 项 |

```bash
# 全部
python -m pytest tests/unit/ tests/integration/ src/wireless_competition/adversarial/tests/ -v

# 按模块
python -m pytest tests/unit/test_p2.py -v     # P2 专项
python -m pytest tests/unit/test_p3.py -v     # P3 专项
python -m pytest tests/integration/test_dsss_frame.py -v  # DSSS帧级
```

---

## 15. 运行全部测试（163项）

```
tests/unit/test_common.py .................          17 passed
tests/unit/test_file_protocol.py ................    16 passed
tests/unit/test_ml.py ...........                    11 passed
tests/unit/test_p2.py ........................       24 passed
tests/unit/test_p3.py .........                       9 passed
tests/unit/test_tx.py .....................          21 passed
tests/integration/test_dsss_frame.py .......          7 passed
tests/integration/test_end_to_end.py .........        9 passed
tests/integration/test_grc_project.py ..........     10 passed
tests/integration/test_modem_chain.py ......          6 passed
tests/operation/test_operation.py ..........          10 passed
tests/regression/test_regression.py ..                 2 passed
adversarial/tests/test_adversarial.py .........      21 passed
                                                ─────────
                                          TOTAL: 163 passed
```

---

## 16. 单文件 GNU Radio Companion 工程

完整 GRC 工程位于 [`gnu_radio_contest_grc/sdr_contest_complete.grc`](gnu_radio_contest_grc/sdr_contest_complete.grc)，使用五个 Embedded Python Blocks 把协议、收发、连续前导搜索、IQ 回放和受门控的 Pluto/NanoSDR 接口保存在同一份 `.grc` 中。

```powershell
cd C:\Users\16839\Desktop\无线电gpt
python -m pip install -e .
cd gnu_radio_contest_grc
gnuradio-companion sdr_contest_complete.grc
```

默认 `role='sim'`，可直接用随附 `input_payload.bin` 做逐字节回环。`role` 还支持 `replay`、`rx` 和 `tx`。真实 TX 默认 fail-closed，必须同时通过显式开关、正式规则 YAML、频率/带宽/时长约束和物理链路确认；始终使用有限、非 cyclic 发送。详细参数与实机清单见 [`gnu_radio_contest_grc/README.md`](gnu_radio_contest_grc/README.md)。
