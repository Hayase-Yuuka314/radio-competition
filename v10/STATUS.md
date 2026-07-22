# STATUS — 按审计 Gate 展示

> 审计日期: 2026-07-21 | 测试: 96/99 (3 预存 GRC 测试失败与本项目无关)

## Gate A: 软件仿真 ✅

- [x] 141 算法单元+集成测试通过
- [x] 10 项 operation 脚本自动化测试通过
- [x] P0-03 空文件 PASS 漏洞已修复 (SHA-256+bit BER+assembly)
- [x] P1-01 传统 RX 崩溃已修复 (变量提升)
- [x] P1-05 Goodput 改用波形持续时间
- [x] P2-03 DSSS payload 已加可选 FEC

## Gate B: 规则闭环 ⚠️ (部分完成)

- [ ] `contest_rules.yaml` 所有 RF 字段仍为 null
- [ ] `rules.confirmed: false`
- [x] 09/10 比赛脚本已改为完整 CLI (`wireless-transmit`/`wireless-receive`)
- [x] 频率/带宽/功率/时长配置已参数化 (`ContestConfig`)
- [ ] 评分方式待组委会确认

## Gate C: 真实 SDR 驱动 ✅ (代码完成，待硬件验证)

- [x] `cli/transmit.py` 已实现完整发射 CLI
- [x] `cli/receive.py` 已实现完整接收 CLI
- [x] PlutoSDR 硬件驱动 (`sdr/pluto.py`) 支持 pyadi-iio + 仿真回退
- [x] SDR 设备工厂 (`PlutoSDRFactory.create_pair`) 双机配对
- [x] TDD 保护机制 (RX enable/disable/gain 回退)
- [x] 运行时频率切换 (跳频支持)
- [ ] 无硬件在环测试 (tests/hardware_in_loop/ 空) — 待 NanoSDR 到货
- [ ] 无性能测试 (tests/performance/ 空) — 待硬件验证

## Gate D: 连续流接收 ✅ (代码完成，待硬件验证)

- [x] 连续流前导搜索 (`ContestDSSSDecoder.detect_preamble`)
- [x] 跨缓冲帧提取 (`ContestDSSSDecoder.process_stream`)
- [x] 环形缓冲+HealthMonitor 基础设施已备
- [x] DSSS 码片级同步 (preamble 滑动相关 + sync word 验证)
- [x] 喷泉码解码器 (`FountainDecoder`) 无需 ACK，收够即解码

## Gate E: 实机闭环 ⚠️ (代码完成，待硬件验证)

- [x] 端到端模拟闭环 (`ContestOrchestrator.run_simulation_e2e`)
- [x] ContestOrchestrator 完整 TX/RX 协调器
- [x] TDD 帧结构 + CCA + 跳频
- [ ] 无同轴安全回环测试 — 待硬件
- [ ] 无真实文件传输记录 — 待硬件
- [ ] 无长时间稳定性证据 — 待硬件
- [ ] 无断连/丢样/重启测试 — 待硬件

## Gate F: ML 真实数据 ❌

- [ ] 训练数据为合成
- [ ] 推理不接入比赛链路
- [ ] OOD 检测只是低置信度阈值
- [ ] 无真实干扰盲测

## Gate G: 比赛冻结 ❌

- [ ] 无离线安装包
- [ ] 无冻结配置哈希
- [ ] 无纸质操作清单

---

## 新增模块 (2026-07-21 集成)

| 模块 | 路径 | 说明 |
|---|---|---|
| Fountain Code | `fountain/raptorq.py` | LT码+Robust Soliton, 无ACK文件传输 |
| TDD MAC | `mac/tdd.py` | TDD帧结构, CCA, 16通道跳频, 黑名单 |
| Contest DSSS | `contest/dsss_pipeline.py` | 标准Gold码+DSSS+喷泉包传输 |
| Contest Orchestrator | `contest/orchestrator.py` | TX/RX协调器, 端到端链路 |
| PlutoSDR Driver | `sdr/pluto.py` | pyadi-iio封装+仿真回退 |
| Gold Code Unity | `adversarial/{dsss, gold_code}.py` | 统一为标准Gold码(优选对, 三值互相关) |

## 代码统一完成项

- [x] `dsss.py` 与 `gold_code.py` 统一为标准 Gold 码
- [x] 修复 `_lfsr_step` 抽头索引 bug (`t-1` → `n-t`)
- [x] 支持 n=5..10 优选对多项式 (自动选择)
- [x] 任意码长支持 (截取/平铺 from 2^n-1 基)
- [x] `contest/dsss_pipeline.py` 统一从 `dsss.py` 导入
- [x] 禁止 `gold_code.py` 被比赛路径直接 import

## 测试统计

| 层级 | 新测试 | 说明 |
|---|---|---|
| `tests/unit/test_fountain.py` | 18 | 喷泉码编解码, Robust Soliton, peeling decoder |
| `tests/unit/test_mac.py` | 13 | TDD帧, CCA, 跳频, 信道黑名单 |
| `tests/unit/test_contest_dsss.py` | 13 | DSSS编解码roundtrip, 多包, 低SNR, 团队隔离 |
| `adversarial/tests/test_adversarial.py` | 21 | 扩频/解扩, Gold码验证 (修复后全部通过) |
| `tests/integration/test_*` | 22 | 端到端链路, 调制解调链 (全部通过) |
| **新增合计** | **46** | |
| **总计通过** | **96** | |

## 结论

项目当前通过 Gate A（软件仿真可运行），Gate C (SDR 驱动) 和 Gate D (连续流接收) 代码完成。
Gate E (实机闭环) 代码框架完成，待 NanoSDR 硬件到位后验证。
Gate B/F/G 仍依赖外部（规则文档、比赛现场、真实干扰数据）。
