# STATUS — 按审计 Gate 展示

> 审计日期: 2026-07-21 | 测试: 163/163

## Gate A: 软件仿真 ✅

- [x] 132 算法单元+集成+回归测试通过（含 10 项 GRC/连续流专项）
- [x] 10 项 operation 脚本自动化测试通过
- [x] 21 项 adversarial/DSSS 测试通过
- [x] P0-03 空文件 PASS 漏洞已修复 (SHA-256+bit BER+assembly)
- [x] P1-01 传统 RX 崩溃已修复 (变量提升)
- [x] P1-05 Goodput 改用波形持续时间
- [x] P2-03 DSSS payload 已加可选 FEC
- [x] QPSK 接收按 bits-per-symbol 正确计算 payload 容量
- [x] `SimulationReceiver` 使用调用方传入的 guard

## Gate B: 规则闭环 ❌

- [ ] `contest_rules.yaml` 所有 RF 字段仍为 null
- [ ] `rules.confirmed: false`
- [ ] 09/10 比赛脚本未加载规则校验
- [ ] 频率/带宽/功率/时长/评分 均待组委会确认

## Gate C: 真实 SDR 驱动 ❌

- [ ] `cli/transmit.py` 为 stub
- [ ] `cli/receive.py` 为 stub
- [ ] 09/10 非 `--sim` 路径为占位注释
- [x] 单文件 GRC 内含受门控的 pyadi-iio 有限 TX/RX block
- [ ] GRC pyadi-iio block 尚无真实设备验证
- [ ] 无硬件在环测试 (tests/hardware_in_loop/ 空)
- [ ] 无性能测试 (tests/performance/ 空)

## Gate D: 连续流接收 ⚠️

- [x] 公共 `Receiver` 已用采样率前导相关切分连续多帧
- [x] GRC 支持跨 work-buffer 累积和无 tag IQ 回放相关搜索
- [x] 任意缓冲偏移的单载波前导搜索已有确定性集成测试
- [ ] `SimulationReceiver` 仍是按设计使用已知帧边界的单帧测试器
- [ ] DSSS 接收假设码片严格分组
- [ ] 无码片定时恢复

## Gate E: 实机闭环 ❌

- [ ] 无同轴安全回环测试
- [ ] 无真实文件传输记录
- [ ] 无长时间稳定性证据
- [ ] 无断连/丢样/重启测试

## Gate F: ML 真实数据 ❌

- [ ] 训练数据为合成
- [ ] 推理不接入比赛链路
- [ ] OOD 检测只是低置信度阈值
- [ ] 无真实干扰盲测

## Gate G: 比赛冻结 ❌

- [ ] 无离线安装包
- [ ] 无冻结配置哈希
- [ ] 无纸质操作清单

## 结论

项目当前通过 Gate A（软件仿真可运行），Gate D 的单载波连续流路径已完成并测试，DSSS 码片同步仍未完成。
Gate B、C、E、F、G 仍需正式规则、RadioConda/GNU Radio、NanoSDR 硬件和实测证据后才能通过。
