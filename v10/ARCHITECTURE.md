# 软件架构全景图

> 只描述已实现的代码路径。❌ = 未实现。✅ = 已实现。⚠️ = 部分实现。
> 更新: 2026-07-21 — 喷泉码 + TDD MAC + 标准Gold码统一 + PlutoSDR驱动

## 整体数据流 (比赛模式)

```
                              ┌──────────┐
                              │ 原始文件  │
                              └────┬─────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │   Fountain Encoder          │
                    │   LT码 + Robust Soliton      │
                    │   无ACK, 无限编码包流         │
                    │   fountain/raptorq.py ✅     │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │   Contest DSSS Encoder       │
                    │   标准Gold码 (SF=128)         │
                    │   Preamble + Sync + Payload  │
                    │   contest/dsss_pipeline.py ✅│
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │   TDD MAC Controller         │
                    │   CCA → TX → Guard → RX      │
                    │   16通道跳频 + 黑名单         │
                    │   mac/tdd.py ✅              │
                    └──────────────┬──────────────┘
                                   │
               ┌───────────────────┼───────────────────┐
               │                   │                   │
     ┌─────────▼─────────┐ ┌──────▼───────┐ ┌─────────▼─────────┐
     │  PlutoSDR TX      │ │   无线信道    │ │  PlutoSDR RX      │
     │  + 2.4GHz BPF     │ │   (竞争干扰)  │ │   (无外置滤波器)   │
     │  sdr/pluto.py ✅  │ │   ❌ 真实环境 │ │  sdr/pluto.py ✅  │
     └───────────────────┘ └──────┬───────┘ └─────────┬─────────┘
                                  │                   │
                    ┌─────────────▼───────────────────▼─────────────┐
                    │   Contest DSSS Decoder                        │
                    │   前导滑动相关 → Sync验证 → 解扩 → 喷泉包提取  │
                    │   contest/dsss_pipeline.py ✅                  │
                    └──────────────────────┬───────────────────────┘
                                           │
                    ┌──────────────────────▼───────────────────────┐
                    │   Fountain Decoder                           │
                    │   Peeling + Gaussian Elimination             │
                    │   收够K+overhead包 → 解码 → 文件              │
                    │   fountain/raptorq.py ✅                     │
                    └──────────────────────┬───────────────────────┘
                                           │
                                      ┌────▼────┐
                                      │ 恢复文件 │
                                      └─────────┘
```

---

## 各层详细状态

### 0. 新增模块 (2026-07-21)

| 模块 | 文件 | 状态 | 说明 |
|---|---|---|---|
| **Fountain Code** | `fountain/raptorq.py` | ✅ | LT码 (Robust Soliton), 系统码+K冗余包, Peeling+Gaussian decoder |
| **TDD MAC** | `mac/tdd.py` | ✅ | Superframe: CCA→TX→RX→Guard, 16通道跳频, 信道黑名单 |
| **Contest DSSS** | `contest/dsss_pipeline.py` | ✅ | 标准Gold码+喷泉包+DSSS, 前导搜索+Sync验证 |
| **Contest Orchestrator** | `contest/orchestrator.py` | ✅ | 竞赛TX/RX协调器, transmit_file/receive_file/run_simulation_e2e |
| **PlutoSDR Driver** | `sdr/pluto.py` | ✅ | pyadi-iio封装, 仿真回退, TDD保护(RX enable/disable/gain), 动态跳频 |

### 1. 发送端 (tx/) — 传统链路 (仿真用)

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

### 3. 接收端 (rx/) — 传统链路 (仿真用)

| 模块 | 状态 | 说明 |
|---|---|---|
| `detector.py` | ⚠️ | FrameDetector: PN前导相关检测。仿真中可用，连续流中未经测试 |
| `cfo.py` | ✅ | CFO估计(前导/导频)+校正 |
| `timing.py` | ✅ | Gardner定时恢复 + 前导定时相关 |
| `carrier.py` | ✅ | Costas环 BPSK/QPSK 相位跟踪 |
| `filters.py` | ✅ | IIR陷波器 + Butterworth带通 |
| `demodulation.py` | ✅ | 硬/软解调, EVM/噪声标准差估计 |
| `decoder.py` | ✅ | 去交织+Viterbi译码+CRC校验 |
| `pipeline.py` | ⚠️ | Receiver: 完整接收链。调用者需提供已切好的帧数组 |
| `sim_receiver.py` | ⚠️ | SimulationReceiver: 文档明确依赖已知帧边界 |
| `equalizer.py` | ✅ | LMS均衡器，训练+判决引导双模式 |

### 4. 文件协议 (file_protocol/) — 被喷泉码替代

| 模块 | 状态 | 说明 |
|---|---|---|
| `chunker.py` | ⚠️ | 文件分块。**比赛路径使用 FountainEncoder 替代** |
| `frame_header.py` | ✅ | 14字节帧头, CRC-CCITT |
| `integrity.py` | ✅ | CRC-32, CRC-8 |
| `assembler.py` | ⚠️ | **比赛路径使用 FountainDecoder 替代** |

### 5. 对抗通信 (adversarial/) — 已统一

| 模块 | 状态 | 说明 |
|---|---|---|
| `dsss.py` | ✅ | 扩频/解扩引擎。**已统一：委托 gold_code.py 生成标准Gold码** |
| `gold_code.py` | ✅ | 标准Gold码 (n=5..10 优选对+循环移位), 三值互相关担保。**比赛和仿真均从此生成** |
| `waveform.py` | ✅ | AdversarialWaveform + FrameRandomizer |
| `strategy.py` | ✅ | 四层策略控制器(防御/频谱占据/动态码长/跳码) |
| `evaluation.py` | ✅ | DSSS性能评估(己方vs对手BER, 多队SIR扫描) |
| `link.py` | ✅ | DSSS简化链路: payload+CRC→扩频→信道→解扩→CRC验证 |
| `frame.py` | ⚠️ | DSSS完整帧。**比赛用 contest/dsss_pipeline.py 替代** |
| `pipeline.py` | ⚠️ | **比赛用 contest/orchestrator.py 替代** |

### 6. 机器学习 (ml/ + features/)

| 模块 | 状态 | 说明 |
|---|---|---|
| `features/time_domain.py` | ✅ | 47维特征(时域+频域+接收机)。训练用SNR/CFO真值，推理不提供 |
| `ml/dataset.py` | ✅ | 7类合成干扰×capture防泄漏划分 |
| `ml/random_forest.py` | ⚠️ | 随机森林+Platt校准。OOD=低置信度阈值，非真正分布外检测 |

### 7. SDR 硬件层 (sdr/)

| 模块 | 状态 | 说明 |
|---|---|---|
| `base.py` | ✅ | SDRDevice抽象类 + SimulatedSDRDevice + FileReplaySDRDevice |
| `pluto.py` | ✅ | PlutoSDRDevice (pyadi-iio), PlutoSDRFactory (双机配对), 仿真回退 |

### 8. CLI 命令行

| 入口 | 状态 | 说明 |
|---|---|---|
| `simulate.py` | ✅ | 端到端仿真 CLI |
| `transmit.py` | ✅ | 比赛发射 CLI: `wireless-transmit <file> --team-id N [--sim]` |
| `receive.py` | ✅ | 比赛接收 CLI: `wireless-receive --team-id N [--output out.bin]` |
| `generate_dataset.py` | ✅ | 数据集生成 CLI |
| `train_classifier.py` | ✅ | 训练分类器 CLI |
| `evaluate.py` | ✅ | Monte Carlo 评估 CLI |

### 9. 公共基础设施 (common/)

| 模块 | 状态 | 说明 |
|---|---|---|
| `types.py` | ✅ | 40+ dataclass/枚举 (含 ContestConfigData, TransmissionReport 等) |
| `config.py` | ✅ | YAML合并+RF校验+配置哈希 |
| `seeds.py` | ✅ | 可复现RNG+派生种子 |
| `logging.py` | ✅ | 结构化日志 |
| `validation.py` | ✅ | NaN/Inf/Nyquist检查 |
| `buffer.py` | ✅ | 线程安全环形缓冲+HealthMonitor |
| `recovery.py` | ✅ | safe_call重试/IQ消毒/参数校验 |

---

## 测试体系

| 层级 | 路径 | 数量 | 覆盖 |
|---|---|---|---|
| 单元 | `tests/unit/` | 65+44=109 | common/file_protocol/tx/ml/p2/p3/fountain/mac/dsss |
| 集成 | `tests/integration/` | 22 | end_to_end/dsss_frame/modem_chain/grc_project |
| 对抗 | `adversarial/tests/` | 21 | DSSS扩频/策略/评估 (全部通过) |
| 操作 | `tests/operation/` | 10 | operation脚本 |
| HIL | `tests/hardware_in_loop/` | 0 | 空 — 待硬件 |
| 性能 | `tests/performance/` | 0 | 空 — 待硬件 |

**总计: 96 passed (3 预存 GRC 测试失败与本项目无关)**

---

## 未实现的关键路径 (按审计Gate排列)

```
Gate A: 软件仿真 ────────────── ✅ 完成 (96 测试通过)
  │
Gate B: 规则闭环 ────────────── ⚠️ RF字段待组委会确认, 代码+CLI已完成
  │
Gate C: 真实SDR驱动 ─────────── ✅ 代码完成 (待硬件验证)
  │
Gate D: 连续流接收 ──────────── ✅ 代码完成 (待硬件验证)
  │
Gate E: 实机闭环 ────────────── ⚠️ 代码框架完成 (待硬件)
  │
Gate F: ML真实数据 ──────────── ❌ 合成训练, 推理不接入链路
  │
Gate G: 比赛冻结 ────────────── ❌ 无离线安装包/压力测试/操作清单
```
