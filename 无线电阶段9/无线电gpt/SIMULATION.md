# 模拟程序架构、有效性论证与现实对接

> 文件性质：所有模拟程序的内部架构、编写规范、有效性验证方法、与现实场景的映射关系。
> 版本：v1.0 | 日期：2026-07-20 | 后续模拟程序持续追加

---

## 目录

1. [模拟程序全景图](#1-模拟程序全景图)
2. [内部架构与编写规范](#2-内部架构与编写规范)
3. [模拟有效性论证](#3-模拟有效性论证)
4. [仿真到现实的域迁移](#4-仿真到现实的域迁移)
5. [各模拟程序详解](#5-各模拟程序详解)
6. [新增模拟程序清单模板](#6-新增模拟程序清单模板)

---

## 1. 模拟程序全景图

项目共 22 个模拟相关模块，分四级：

| 层级 | 数量 | 包含 |
|---|---|---|
| **S1 CLI 入口** | 6 | `simulate.py`, `transmit.py`, `receive.py`, `generate_dataset.py`, `train_classifier.py`, `evaluate.py` |
| **S2 库模块** | 12 | `channel/*`(4), `adversarial/*`(5), `rx/sim_receiver.py`, `features/time_domain.py`, `ml/*`(2) |
| **S3 Demo 脚本** | 3 | `demo_waveform.py`, `demo_adversarial.py`, `demo_ml.py` |
| **S4 测试** | 1 | `adversarial/tests/test_adversarial.py` (独立) + `tests/unit/`, `tests/integration/` |

**数据流**：S2 库模块 → S1 CLI / S3 Demo → 用户。S4 测试验证 S2。

---

## 2. 内部架构与编写规范

### 2.1 通用架构模式

每个模拟程序遵循统一的四层模式：

```
┌─────────────────────────────────────────┐
│  配置层                                   │
│  configs/*.yaml → ChannelConfig /        │
│  RxProfile / AdversarialStrategy         │
├─────────────────────────────────────────┤
│  数据生成层                               │
│  TXPipeline / generate_dataset /         │
│  dsss_transmit / _random_binary_data     │
├─────────────────────────────────────────┤
│  处理层                                   │
│  ChannelPipeline / SimulationReceiver /  │
│  InterferenceClassifier / despread       │
├─────────────────────────────────────────┤
│  输出层                                   │
│  metrics.json / .png 图表 /              │
│  DecodeResult / evaluation dict          │
└─────────────────────────────────────────┘
```

### 2.2 编写规范（11 条强制规则）

以下是所有模拟程序必须遵守的规则，来自备赛计划文档第 0.2 节和第 25 节：

| # | 规则 | 检查方式 |
|---|---|---|
| 1 | 所有随机过程使用独立 RNG（`np.random.Generator`），保存种子 | `common/seeds.py` 的 `create_rng(seed)` |
| 2 | 每个模块有明确输入类型、输出类型、单位 | 类型标注 + docstring |
| 3 | 参数不可写死，走 YAML 配置或构造函数 | `configs/*.yaml` → `ChannelConfig`/`RxProfile` |
| 4 | 未知赛制字段保持 `null`，纯软件仿真不受限 | `contest_rules.yaml` + `validate_rf_for_tx()` |
| 5 | NaN/Inf 有兜底策略（特征→0，信号→报错） | `_safe()` + `check_finite()` |
| 6 | 每个模块有独立单元测试 | `tests/unit/` |
| 7 | 端到端链路有回归测试（固定种子+预期范围） | `tests/integration/` + `tests/regression/` |
| 8 | 每次实验保存完整配置、种子、结果 | `save_resolved_config()` + 实验目录模板 |
| 9 | 可视化必须含中文标注、通俗图例、数据来源 | `demo_*.py` |
| 10 | 模型失败有回退路径（ML→规则→默认配置） | `confidence_threshold` + `is_ood` + fallback |
| 11 | 空口发射前必须通过 RF 安全校验 | `validate_rf_for_tx()` |

### 2.3 代码模式示例

**模式 A：库模块（S2 级）**

```python
class MySimulator:
    """一句话职责。"""
    def __init__(self, param: float = 1.0, seed: Optional[int] = None):
        self.param = param
        self._rng = create_rng(seed)

    def process(self, input: np.ndarray) -> ResultType:
        """输入→处理→输出。"""
        check_finite(input, "input")
        # ... 处理逻辑 ...
        return ResultType(...)
```

**模式 B：Demo 脚本（S3 级）**

```python
def plot_xxx(data) -> plt.Figure:
    """生成 matplotlib 图表。含中文标题、图例、数据标注。"""
    fig, axes = plt.subplots(...)
    axes[0].set_title("中文标题", fontweight="bold")
    return fig

def export_all(output_dir): ...
def run_demo(): ...

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", action="store_true")
    args = ap.parse_args()
    if args.export: export_all()
    else: run_demo()
```

---

## 3. 模拟有效性论证

### 3.1 有效性层次

模拟程序的有效性分三级验证：

| 层次 | 验证内容 | 方法 | 已覆盖程序 |
|---|---|---|---|
| **L1 理论一致** | 仿真结果 vs 理论公式 | BPSK BER vs Q(√(2Eb/N0)) 曲线对比 | `test_modem_chain.py` |
| **L2 可复现性** | 固定种子多次运行完全一致 | pytest + 固定 seed + assert | 所有 S2/S4 程序 |
| **L3 边界压力** | 极端参数下的行为（SNR=-20dB, SNR=100dB, 零长度, 超长） | Monte Carlo + 参数扫描 | `evaluate_dsss_performance()` |

### 3.2 各模块有效性证据

#### 3.2.1 传统通信链路

| 验证项 | 方法 | 证据 |
|---|---|---|
| BPSK 调制解调往返 | `bytes→bits→BPSK→AWGN→解调→bits→bytes` | `test_modem_chain.py`: 无噪声100%恢复 |
| AWGN BER 趋势 | 不同 SNR 下 BER 单调下降 | `test_end_to_end.py::test_ber_decreases_with_snr`: 严格单调 |
| 卷积码编码增益 | 同 SNR 下编码 BER < 无编码 BER | `test_modem_chain.py::test_convolutional_awgn` |
| 帧级全链路 | TX→ChannelPipeline→RX 逐字节恢复 | `test_end_to_end.py`: SNR=5dB, 9/9 通过 |
| RRC 脉冲成形 | 能量归一化 + 匹配滤波输出 | `test_tx.py::test_rrc_energy`: 能量=1.0 |

#### 3.2.2 DSSS 对抗通信

| 验证项 | 方法 | 证据 |
|---|---|---|
| 扩频解扩往返 | `spread(despread(x)) == x` | `test_adversarial.py`: 21/21 通过 |
| 不同码不互通 | 队0码扩频→队1码解扩 BER≈50% | `test_different_codes_dont_work` |
| Gold 码互相关 | 任意两队码互相关 < 0.1 | `test_rival_signal_orthogonal` |
| 处理增益 | 码长 255 → BER@SNR=-5dB < 1% | `test_awgn_resilience` |
| 多队干扰鲁棒 | 3对手各强20dB → 己方BER < 5% | `test_multiteam` |
| DSSS 简化链路 | SNR=-10dB → 500B全部恢复 | 手动验证 `dsss_end_to_end` |

#### 3.2.3 ML 干扰分类器

| 验证项 | 方法 | 证据 |
|---|---|---|
| 数据集无泄漏 | capture_id 分组划分，train∩test=∅ | `test_split_no_leakage` |
| 分类优于随机 | 7类准确率 > 50% (随机=14%) | `test_accuracy_above_chance` |
| 模型持久化 | save→load→predict 一致 | `test_save_load` |
| 核心类 F1 | 单音/多音/扫频/宽带噪声 F1≈1.0 | `demo_ml.py` 评估报告 |

### 3.3 可复现性保证

```
种子链路：
  contest_rules.yaml/CLI --seed=X
    → set_base_seed(X)
      → create_seed_sequence(N, X) → N 个独立派生种子
        → create_rng(seed_i) → 每个模块的独立 RNG
          → 所有随机操作可精确重放
```

验证命令：
```bash
# 两次运行结果完全一致
python -m wireless_competition.cli.simulate --seed 42 --snr-db 10
python -m wireless_competition.cli.simulate --seed 42 --snr-db 10
# → metrics.json 中所有数值完全相同
```

---

## 4. 仿真到现实的域迁移

### 4.1 仿真与现实的主要差异

| 差异维度 | 仿真假设 | 现实情况 | 缓解措施 |
|---|---|---|---|
| 噪声模型 | AWGN (高斯白噪声) | 非白、有色、非平稳 | 参数随机化 + 真实IQ测试集 |
| 干扰类型 | 训练7类已知干扰 | 可能有未知干扰 | OOD检测 + 回退默认配置 |
| SDR 硬件 | 理想线性器件 | DC偏移/IQ失衡/相噪/时钟误差 | `impairments.py` 9种损伤已建模 |
| 信道 | 静态/可配置 | 时变、人员移动 | 缓慢时变增益 + Monte Carlo |
| 采样 | 连续无丢失 | USB丢样/缓冲区溢出 | `apply_drop_samples` + 环形缓冲(待实现) |
| 天线 | 理想全向 | 频响不平坦、极化、遮挡 | 不同增益 + 滤波器响应 |
| 对手 | 7类仿真干扰 | 未知波形、时变策略 | OOD回退 + DSSS天然抗干扰 |

### 4.2 域迁移策略（三步走）

```
步骤 1: 仿真中参数随机化
  ├── SNR/INR/CFO 在合理范围内随机抽取
  ├── 干扰类型随机混合
  ├── 增益/相位随机
  └── 丢样/削顶随机注入

步骤 2: 真实 IQ 采集构建盲测集
  ├── 无线电静默背景采集
  ├── 仅期望信号采集
  ├── 真实 SDR 环回采集
  └── 按 session 分组划分（防泄漏）

步骤 3: 评估+微调
  ├── 仿真模型 vs 真实盲测性能对比
  ├── 仅在有证据时微调模型
  ├── 保留原始 IQ 供复盘
  └── 两个频段 (433MHz/2.4GHz) 分别报告
```

### 4.3 仿真参数→比赛参数映射

| 仿真参数 | 比赛对应 | 当前状态 |
|---|---|---|
| `snr_db` | 信号功率/噪声功率 | 待规则确认 |
| `cfo_hz` | TX/RX 本振偏差 | 待 NanoSDR 实测 |
| `sample_rate_hz` | SDR 采样率 | 待规则+设备确认 |
| `inr_db` | 对手信号强度 | 取决于现场距离 |
| `interference_type` | 对手波形类型 | 仿真覆盖7类 |
| `code_length` (DSSS) | 扩频因子 | 赛中可动态调整 |

---

## 5. 各模拟程序详解

### 5.1 `cli/simulate.py` — 端到端仿真 CLI

**架构**：
```
_random_binary_data(seed) → bytes
  → TXPipeline.process_file() → list[IQ frames]
    → ChannelPipeline.apply(frame_iq, ...) → ChannelOutput
      → SimulationReceiver.process_frame(...) → DecodeResult
        → FileAssembler → 恢复文件
          → BER/PER/Goodput 计算 → JSON 报告
```

**有效性**：帧级端到端回归测试 9/9 通过（SNR=5~100dB, BPSK/QPSK, 无FEC/卷积码, 含CFO）。

**现实对接**：`sample_rate_hz` 和 SNR 范围需根据 NanoSDR 实测和比赛规则补全。CFO 参数需实测 TX/RX 本振偏差。

---

### 5.2 `channel/pipeline.py` — 信道模拟流水线

**架构**：
```
ChannelConfig (12种损伤开关+参数)
  → ChannelPipeline.apply(iq, sample_rate_hz, rng):
      AWGN → 多径 → CFO → 定时偏移 → 相位噪声
      → DC偏移 → IQ失衡 → 削顶 → 干扰 → 量化 → 丢样
    → ChannelOutput (iq + ground_truth标签)
```

**有效性**：每种损伤独立开关、独立单元测试、确定性输出（同输入+同种子=同输出）。

**现实对接**：`cfo_hz`/`phase_noise_std_rad`/`iq_gain_imbalance_db` 需从 NanoSDR 实测标定。`enable_drop_samples` 模拟 USB 丢样。

---

### 5.3 `rx/sim_receiver.py` — 仿真接收机

**架构**：
```
过采样IQ → matched_filter(RRC)
  → 前导定位 (guard±span 搜索, PN相关)
    → 同步字验证 (16符号BPSK)
      → CFO估计校正 (Costas环)
        → 包头解码 (224符号→卷积码→14字节→CRC-CCITT)
          → 载荷解调 (BPSK/QPSK, 硬判/软判LLR)
            → FEC译码 → CRC-32校验 → DecodeResult
```

**有效性**：帧级端到端 9/9 通过。前导定位 dot=64.0/64 完美匹配。

**现实对接**：`frame_detection_threshold` 需根据真实 SNR 调整。`guard_symbols` 需匹配发送端。CFO 搜索范围需覆盖实测频偏。

---

### 5.4 `adversarial/dsss.py` — DSSS 扩频引擎

**架构**：
```
Gold码生成 (m序列XOR, 可复现)
  → SpreadingCodeManager (多队伍码管理)
    → spread(bits, code) → chips (±1, len=bits×code_len)
      → [信道] → despread(chips, code) → 软值/硬判比特
```

**有效性**：21 测试全通过。码长 255 → SNR=-10dB 全恢复。Gold 码互相关 < 0.1。

**现实对接**：`team_id` 映射到比赛队伍编号。`code_length` 赛中可根据策略动态调整。

---

### 5.5 `adversarial/link.py` — DSSS 简化链路

**架构**：
```
payload → append_crc32 → bytes_to_bits → BPSK ±1
  → spread(code) → chips
    → AWGN (snr_db) → noisy_chips
      → despread(code) → 软值 → 硬判
        → check_crc32 → (payload, crc_ok)
```

**有效性**：SNR=-10dB (码长255) → 500B全恢复。多队 SIR=-15dB + 3对手 → 通过。

**现实对接**：绕过帧结构的纯载荷验证。完整帧结构对接见 P1 剩余工作。

---

### 5.6 `ml/random_forest.py` — 干扰分类器

**架构**：
```
特征提取 (FeatureExtractor: 37维)
  → StandardScaler → RandomForest (80树, max_depth=12)
    → Platt校准 (CalibratedClassifierCV)
      → predict() → {class, confidence, is_ood}
        → confidence < 0.6 → ood → 回退默认配置
```

**有效性**：7类准确率 90.8%，核心类 F1≈1.0。OOD 门控正常工作。

**现实对接**：需真实 IQ 盲测集验证。模型文件可离线部署（joblib）。

---

### 5.7 `scripts/demo_waveform.py` — 传统波形可视化

**生成图表**：
1. `01_full_pipeline.png` (9面板): 比特→星座→RRC→噪声→干扰→MF→接收星座→误码对比
2. `02_spectrum.png` (4面板): PSD 频域对比
3. `03_filter_detail.png` (4面板): 噪声对比+RRC+MF效果+眼图
4. `04_interference_analysis.png` (4面板): 干扰叠加+MF抗干扰+误码统计

**有效性**：使用真实 DSP 模块生成数据，非绘图示意。

---

### 5.8 `scripts/demo_adversarial.py` — DSSS 可视化

**生成图表**：
1. `adversarial_01_dsss_principle.png` (9面板): 比特→码→码片(含SNR=5dB噪声)→互相关→己方/对手解扩→频谱→星座(含噪声抖动)→BER曲线
2. `adversarial_02_multiteam.png` (4面板): 四队码对比+互相关矩阵+SIR-BER+策略时间线

**有效性**：使用 `SpreadingCodeManager`/`evaluate_dsss_performance` 等真实模块。

---

### 5.9 `scripts/demo_ml.py` — ML 可视化

**生成图表**：
1. `ml_01_classifier_report.png` (3面板): 混淆矩阵+特征重要性Top15+每类F1

**有效性**：真实数据集生成+真实模型训练，报告实际性能指标。

---

### 5.10 `gnu_radio_contest_grc/sdr_contest_complete.grc` — 单文件流式竞赛链路

**架构**：

```text
文件 -> 分块/帧头CRC/FEC -> BPSK/QPSK/RRC
     -> GNU Radio Channel Model(AWGN/CFO/SRO/多径)
     -> 单音/突发/IQ失衡/DC/削顶
     -> tag 对齐快速路径或连续前导相关回退
     -> 解调/FEC/CRC/去重重排 -> 完整文件
```

同一 GRC 通过 `role` 支持 `sim`、`replay`、`tx`、`rx`。硬件接口由 Embedded Python Block 延迟导入 pyadi-iio，因此仿真/回放不要求连接设备；TX 只有在规则、用户开关和物理链路三重确认后才会初始化，且强制非 cyclic、有限时长并在退出时销毁 buffer。

**关键参数**：

| 参数 | 默认值 | 含义 |
|---|---:|---|
| `samp_rate` | 2 MHz | 复基带采样率 |
| `samples_per_symbol` | 8 | RRC 过采样倍数 |
| `modulation` | BPSK | BPSK/QPSK |
| `fec_mode` | convolutional | 无 FEC 或 K=7 rate-1/2 卷积码 |
| `snr_db` | 30 dB | 仿真信噪比 |
| `cfo_hz` / `sro_ppm` | 0 / 0 | 载波与采样钟偏差 |
| `max_capture_samples` | 10,000,000 | 连续捕获内存硬上限 |

**有效性验证**：

| 验证项 | 方法 | 状态 |
|---|---|---|
| GRC YAML、8 条连接、5 个 EPB | 静态解析与源码编译 | ✅ |
| BPSK/QPSK × 无 FEC/卷积 FEC | 随机二进制逐字节端到端 | ✅ |
| 连续 IQ 无 tag 回放 | 三帧拼接、前导相关、CRC 重组 | ✅ |
| 非默认 guard | 24 符号回归 | ✅ |
| TX fail-closed | 默认参数必须抛出拒绝 | ✅ |
| GRC GUI / `grcc` | 当前终端无 GNU Radio | 待 RadioConda 复验 |
| NanoSDR HIL | 当前无硬件 | 待实机复验 |

**现实对接**：仿真 IQ、回放 IQ 和硬件 RX 共用同一解码/指标路径。硬件采集记录 URI、请求值和读回值；只有完整、CRC 有效的全部块才原子生成评分文件，未收齐时只保存独立块文件。

---

## 6. 新增模拟程序清单模板

后续新增模拟程序时，按以下模板添加到本文档：

```markdown
### 6.X `path/to/new_module.py` — 一句话描述

**架构**：
```
输入 → 步骤1 → 步骤2 → ... → 输出
```

**关键参数**：
| 参数 | 默认值 | 含义 |

**有效性验证**：
| 验证项 | 方法 | 状态 |
|---|---|---|

**现实对接**：（如何从仿真参数映射到比赛参数）

**状态**：✅ 完成 / 🔧 开发中 / 📋 计划
```

---

> **维护规则**：每次新增或修改模拟程序后，同步更新本文档对应章节和第 6 节的清单。
