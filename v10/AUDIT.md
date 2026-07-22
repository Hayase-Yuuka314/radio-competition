# 架构安全审计 — 全栈漏洞分析

## CRITICAL (实机必炸)

### G1: 无频偏校正 (dsss_pipeline.py / pluto.py)

PlutoSDR 晶振 20ppm @2.4GHz = **±48kHz** 频偏。
DSSS 解扩是 chip-by-chip dot product：
  - 48kHz 偏 → 每 chip 相位旋转 8.6°
  - 128 chip → 累计 1100° → dot 能量归零 → **解扩完全失败**

**当前状态**: 代码中无任何 CFO 估计/校正。
**仿真**: 不存在此问题（无晶振偏差）。
**实测**: 收发机必须同厂家/同批次才能靠运气对齐。
**修复**: 在 `decode_frame` 前对前导段做粗 CFO 估计（phase difference method）。

### G2: hash 包只发一次 (raptorq.py:187-195)

`encode_systematic_stream()` 第一个包是 hash 包。如果 DSSS 没检测到这个包（前导漏检 / 噪声 / buffer 截断），`_expected_hash = None` → `decode()` **跳过 SHA256 验证** → CRC 通过但文件错误的数据被接受。

**修复**: hash 包在每个 superframe 开始时重发，或编码到每个系统包的 header 中。

### G3: TX/RX 跳频不同步 (mac/tdd.py + orchestrator.py)

`FrequencyHopper.next()` 基于帧计数跳。TX 和 RX 超帧起始时间不同 → 跳频序列脱节 → 通信中断。

**当前**: TX `_tx_slot` 调 `set_frequency()`，但 RX `_rx_slot` **不调** → RX 永远停在初始频点。
**修复**: RX 端也加 `set_frequency()`，或 RX 在所有 16 个频道轮询（扫频模式）。

---

## HIGH (仿真未见但实机可能)

### G4: 前导码在噪声中漏检 (dsss_pipeline.py:195-225)

256 chip 前导 + 0.5 阈值 = 至少 128/256 匹配。SNR=5dB 时匹配度可能低于 128 → 漏检。
多队干扰叠加后，等效信噪比更差 → 前导检测率下降。

**修复**: 降低阈值至 0.35（90/256）并加强 sync 验证；或增加前导长度到 512 chip。

### G5: buffer 边界丢包 (dsss_pipeline.py:230-250)

`process_stream` 一次处理全部数据。`decode_frame` 在 buffer 末尾检查 `remaining_chips < chips_needed` → 返回 None → 包永久丢失。
喷泉码可容忍但增加 5-15% 开销。

**修复**: 使用滑动窗口 + 重叠处理（已做，但 buffer 边界策略可优化）。

### G6: 系统包长度固定导致弱包同大小 (dsss_pipeline.py:106-108)

每个喷泉系统包序列化后 = 20B header + (block_size+4)B payload = 固定长度。
所有帧大小相同 → 前导间距离固定 → 误检测可能周期性累积。

**影响**: 低 SNR 下误检率高于随机帧长度。
**修复**: 接受（喷泉码容忍误检——CRC 会过滤掉假包）。

---

## MEDIUM (边缘情况)

### G7: CCA 功率单位是 dBFS 不是 dBm (mac/tdd.py:341-345)

`measure_channel_power` 返回相对于 ADC 满量程的 dB 值。
-65 dBFS = 信号幅度 = 10^(-65/20) = 5.6e-4 × full scale。
但这个值对应的实际 dBm 取决于 RX gain（40dB）和天线/前端链路衰减。
**RX gain 改变后 -65 dBFS 的物理含义完全改变。**

**修复**: 用已知校准信号标定，或用相对阈值（高于噪底 X dB）。

### G8: Guard 时长边缘 (mac/tdd.py:38)

TX → RX 切换只留 5ms Guard。PlutoSDR 频率切换时间 ~1ms，但 RX AGC/FLL 重新锁定可能需要 >5ms。
实机测试中可能看到切换后的前几个 ms 数据无效。

**修复**: 增加 Guard 到 10ms，或在 RX slot 开头跳过少量样本。

### G9: 仅支持 1 个 hash 包 (raptorq.py:190)

`_hash_sent` 标志在 `encode_systematic_stream()` 和 `next_packet()` 之间不共享。
如果先用 `encode_systematic_stream()` 发了一轮，再调用 `next_packet()` 会再发一个 hash 包。
**影响**: 低。但如果 RX 重启后收到第二轮的 hash 包，`_expected_hash` 被覆盖。

**修复**: `add_packet` 中 hash 包只接受第一个。

### G10: 跳频时 PlutoSDR set_frequency 可能阻塞 (pluto.py:192-199)

`set_frequency` 在 TDD TX slot 内调用。如果 PlutoSDR 频率切换慢 → TX 有效时间缩短。
实测需确认切换延迟 < 1ms。

**修复**: 在 Guard 期内切换频率，不在 TX/RX 期内。

---

## 安全层检查

| 层 | 机制 | 状态 |
|---|---|---|
| 包级 | CRC-32 (系统包) | ✅ |
| 包级 | 前导+sync 检测 | ✅ |
| 文件级 | SHA256 (hash包) | ⚠️ 只发一次 |
| 帧级 | block_size 验长度 | ✅ |
| 码片级 | Gold 码互相关隔离 | ✅ |
| 频域 | 跳频+黑名单 | ⚠️ 不同步 |
| 时域 | TDD 隔离 | ✅ |
| 功率域 | CCA 空闲检测 | ⚠️ dBFS |

---

## 优先修复计划

| 优先级 | 修复 | 预计工时 |
|---|---|---|
| P0 | 频偏校正 (CFO estimate on preamble) | 2h |
| P0 | hash 包重发 (每个 superframe 开头) | 0.5h |
| P0 | RX 端跳频 (跟随 TX) | 1h |
| P1 | 前导检测阈值可调 | 0.5h |
| P1 | Guard 增加到 10ms | 0.2h |
| P1 | CCA 功率用相对值 | 0.5h |
