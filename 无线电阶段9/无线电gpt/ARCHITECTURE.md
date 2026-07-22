# 软件架构全景图

> 只描述已实现的代码路径。❌ = 未实现。✅ = 已实现。⚠️ = 部分实现。

## 整体数据流

```
                              ┌──────────┐
                              │ 原始文件  │
                              └────┬─────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
    ┌─────────▼─────────┐ ┌───────▼───────┐ ┌─────────▼─────────┐
    │  传统 BPSK/QPSK   │ │  DSSS 扩频    │ │     OFDM          │
    │  (tx/pipeline.py) │ │(adversarial/  │ │  (tx/ofdm.py)     │
    │        ✅          │ │  frame.py) ✅ │ │       ✅          │
    └─────────┬─────────┘ └───────┬───────┘ └─────────┬─────────┘
              │                    │                    │
              └────────────────────┼────────────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │    信道模拟 (channel/)       │
                    │  AWGN/CFO/多径/IQ失衡/丢样   │
                    │  6种干扰/削顶/量化/相位噪声   │
                    │            ✅                │
                    └──────────────┬──────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
    ┌─────────▼─────────┐ ┌───────▼───────┐ ┌─────────▼─────────┐
    │  传统接收机        │ │  DSSS 解扩    │ │    OFDM 解调      │
    │  rx/sim_receiver  │ │  frame.py     │ │  ofdm.demodulate  │
    │  ⚠️ (需要已知帧边界)│ │  ⚠️(需要码片对齐)│ │      ✅           │
    └─────────┬─────────┘ └───────┬───────┘ └─────────┬─────────┘
              │                    │                    │
              └────────────────────┼────────────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │   文件重组 (file_protocol/)   │
                    │   去重/乱序/CRC/断点保存      │
                    │            ✅                │
                    └──────────────┬──────────────┘
                                   │
                              ┌────▼────┐
                              │ 恢复文件 │
                              └─────────┘
```

---

## 各层详细状态

### 1. 发送端 (tx/)

| 模块 | 状态 | 说明 |
|---|---|---|
| `modulation.py` | ✅ | BPSK/QPSK 调制解调，硬/软判决 |
| `pulse_shaping.py` | ✅ | RRC 成形+匹配滤波，upsample/downsample |
| `fec.py` | ✅ | 卷积码(K=7, r=1/2) + 维特比硬/软译码 + 重复码 |
| `interleaver.py` | ✅ | 块交织/去交织 |
| `framing.py` | ✅ | 物理帧: Guard/Preamble/Sync/Header/Pilot/Payload+CRC |
| `pipeline.py` | ✅ | TXPipeline: 文件分块→组帧→脉冲成形 |
| `ofdm.py` | ✅ | BPSK/QPSK-OFDM, IFFT/FFT, CP, 导频线性插值信道估计 |

### 2. 信道 (channel/)

| 模块 | 状态 | 说明 |
|---|---|---|
| `awgn.py` | ✅ | 加性高斯白噪声 |
| `impairments.py` | ✅ | CFO/SRO/DC偏移/IQ失衡/相位噪声/削顶/量化/丢样 |
| `interference.py` | ✅ | 单音/多音/扫频/宽带噪声/带限噪声/突发 共6种 |
| `multipath.py` | ✅ | FIR多径 + Rayleigh衰落抽头 |
| `pipeline.py` | ✅ | ChannelPipeline: 12种损伤统一施加+GroundTruth标签 |

### 3. 接收端 (rx/)

| 模块 | 状态 | 说明 |
|---|---|---|
| `detector.py` | ✅ | FrameDetector: 符号率检测 + 采样率前导定位，连续多帧已测试 |
| `cfo.py` | ✅ | CFO估计(前导/导频)+校正 |
| `timing.py` | ✅ | Gardner定时恢复 + 前导定时相关 |
| `carrier.py` | ✅ | Costas环 BPSK/QPSK 相位跟踪 |
| `filters.py` | ✅ | IIR陷波器 + Butterworth带通 |
| `demodulation.py` | ✅ | 硬/软解调, EVM/噪声标准差估计 |
| `decoder.py` | ✅ | 去交织+Viterbi译码+CRC校验 |
| `pipeline.py` | ✅ | Receiver: 采样率前导搜索→连续多帧切分→完整接收链 |
| `sim_receiver.py` | ⚠️ | SimulationReceiver: 同上，**文档明确依赖已知帧边界** |
| `equalizer.py` | ✅ | LMS均衡器，训练+判决引导双模式 |

### 4. 文件协议 (file_protocol/)

| 模块 | 状态 | 说明 |
|---|---|---|
| `chunker.py` | ✅ | 文件分块+元数据 |
| `frame_header.py` | ✅ | 14字节帧头, CRC-CCITT |
| `integrity.py` | ✅ | CRC-32, CRC-8 |
| `assembler.py` | ⚠️ | FileAssembler: 去重/乱序/断点保存。`_blocks` 为动态属性非正式字段 |

### 5. 对抗通信 (adversarial/)

| 模块 | 状态 | 说明 |
|---|---|---|
| `dsss.py` | ⚠️ | 简化扩频码(随机种子+10阶寄存器)。**非标准Gold码** |
| `gold_code.py` | ✅ | 标准Gold码(优选对+循环移位)。**未被比赛路径使用** |
| `waveform.py` | ✅ | AdversarialWaveform + FrameRandomizer |
| `strategy.py` | ✅ | 四层策略控制器(防御/频谱占据/动态码长/跳码) |
| `evaluation.py` | ✅ | DSSS性能评估(己方vs对手BER, 多队SIR扫描) |
| `link.py` | ✅ | DSSS简化链路: payload+CRC→扩频→信道→解扩→CRC验证 |
| `frame.py` | ⚠️ | DSSS完整帧(前导/包头/分块)。**接收假设码片严格分组** |
| `pipeline.py` | ⚠️ | DSSSTXPipeline/DSSSRXPipeline。**集成度不足，独立使用** |

### 6. 机器学习 (ml/ + features/)

| 模块 | 状态 | 说明 |
|---|---|---|
| `features/time_domain.py` | ✅ | 47维特征(时域+频域+接收机)。**训练用SNR/CFO真值，推理不提供** |
| `ml/dataset.py` | ✅ | 7类合成干扰×capture防泄漏划分 |
| `ml/random_forest.py` | ⚠️ | 随机森林+Platt校准。**OOD=低置信度阈值，非真正分布外检测** |

### 7. SDR 硬件层 (sdr/)

| 模块 | 状态 | 说明 |
|---|---|---|
| `base.py` | ⚠️ | SDRDevice抽象类 + SimulatedSDRDevice + FileReplaySDRDevice |
| Pluto/NanoSDR 驱动 | ⚠️ | `gnu_radio_contest_grc/` 内有受规则门控的 pyadi-iio 有限 TX/RX；待 HIL |

### 8. CLI 命令行

| 入口 | 状态 | 说明 |
|---|---|---|
| `simulate.py` | ✅ | 端到端仿真 CLI |
| `generate_dataset.py` | ✅ | 数据集生成 CLI |
| `train_classifier.py` | ✅ | 训练分类器 CLI |
| `evaluate.py` | ✅ | Monte Carlo 评估 CLI |
| `transmit.py` | ❌ | **Stub: 固定打印错误退出** |
| `receive.py` | ❌ | **Stub: 固定打印错误退出** |

### 9. 公共基础设施 (common/)

| 模块 | 状态 | 说明 |
|---|---|---|
| `types.py` | ✅ | 30+ dataclass/枚举 |
| `config.py` | ✅ | YAML合并+RF校验+配置哈希 |
| `seeds.py` | ✅ | 可复现RNG+派生种子 |
| `logging.py` | ✅ | 结构化日志 |
| `validation.py` | ✅ | NaN/Inf/Nyquist检查 |
| `buffer.py` | ✅ | 线程安全环形缓冲+HealthMonitor |
| `recovery.py` | ✅ | safe_call重试/IQ消毒/参数校验 |

---

## 10. operation/ 用户脚本

| 脚本 | 状态 | 说明 |
|---|---|---|
| `00_check.py` | ✅ | 环境检查 |
| `01_train_ml.py` | ✅ | 合成数据训练ML |
| `02_use_ml.py` | ✅ | ML推理演示(不改变实际配置) |
| `03_simulate.py` | ✅ | 传统仿真 |
| `04_dsss_demo.py` | ✅ | DSSS SNR扫描 |
| `05_visualize.py` | ✅ | 生成全部图表 |
| `06_contest.py` | ✅ | 多队对抗分析 |
| `07_all.py` | ✅ | 一键运行00-06 |
| `08_prepare.py` | ⚠️ | 只检查`import adi`，不检查真实设备 |
| `09_contest_tx.py` | ⚠️ | `--sim`=保存npy，无`--sim`=占位 |
| `10_contest_rx.py` | ⚠️ | `--sim`=读取npy，无`--sim`=占位 |
| `11_contest_e2e.py` | ✅ | 纯软件闭环演练 |

---

## 测试体系

| 层级 | 路径 | 数量 | 覆盖 |
|---|---|---|---|
| 单元 | `tests/unit/` | 65 | common/file_protocol/tx/ml/p2/p3 |
| 集成 | `tests/integration/` | 22 | end_to_end/dsss_frame/modem_chain |
| 对抗 | `adversarial/tests/` | 21 | DSSS扩频/策略/评估 |
| 操作 | `tests/operation/` | 10 | operation脚本 |
| HIL | `tests/hardware_in_loop/` | 0 | **空目录** |
| 性能 | `tests/performance/` | 0 | **空目录** |

**总计: 163 passed**

---

## 未实现的关键路径 (按审计Gate排列)

```
Gate A: 软件仿真 ────────────── ✅ 完成
  │
Gate B: 规则闭环 ────────────── ❌ contest_rules.yaml 全null, 脚本未加载规则
  │
Gate C: 真实SDR驱动 ─────────── ❌ transmit/receive CLI stub, 无pyadi-iio设备类
  │
Gate D: 连续流接收 ──────────── ❌ 接收机依赖已知帧边界, DSSS依赖码片分组
  │
Gate E: 实机闭环 ────────────── ❌ 无同轴测试, 无真实文件传输记录
  │
Gate F: ML真实数据 ──────────── ❌ 合成训练, 推理不接入链路
  │
Gate G: 比赛冻结 ────────────── ❌ 无离线安装包/压力测试/操作清单
```

163 项自动测试覆盖 Gate A 和单载波连续流软件路径。Gate B、C、E、F、G 仍需外部资源（规则文档、RadioConda、NanoSDR 硬件、比赛现场）才能推进。
