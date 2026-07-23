# v11_contest — 比赛级抗干扰 DSSS 通信系统

## 相比 demo 的改进

| 特性 | demo | v11_contest |
|---|---|---|
| 扩频码长 | 31 chip (14.9 dB) | **127 chip (21.0 dB)** |
| 同步序列 | 255 chip | **511 chip** |
| 导频序列 | 127 chip | **255 chip** |
| CFO 捕获音 | 2048 sample | **4096 sample** |
| 数据包大小 | 16 B 文本 | **4096 B 文件块** |
| 文件传输 | 不支持 | **分帧 + 序号 + 重组** |
| 跳频 | 无 | **16 通道 2.405-2.48 GHz** |
| Golg 码隔离 | pseudo-Gold | **标准 Gold + team_id** |
| 白化密钥 | SHA-256 XOR | **SHA-256 XOR (含 file_id)** |
| FEC | 卷积 K=7 R=1/2 | **卷积 K=7 R=1/2 (同，已足够)** |

## 文件说明

| 文件 | 用途 |
|---|---|
| `contest_codec.py` | TX/RX 共用编解码库 |
| `contest_tx.grc` | PlutoSDR 发射端流图 |
| `contest_rx.grc` | PlutoSDR 接收端流图 |

## 工作原理

```
TX端:
test_data.txt
  → SHA-256 生成 file_id
  → 按 4096B 分块，每块打包: [Magic][Ver][FileID][Seq][Total][Len][Payload][CRC32]
  → XOR 白化 (SHA-256 key + seq + file_id)
  → 卷积编码 K=7 R=1/2 + 块交织
  → BPSK 符号 → 127-chip Gold 码 DSSS 扩频
  → 加入 62.5kHz 捕获音 + 511-chip 同步 + 255-chip 导频
  → 循环发送 (含包间隔静默)
  → PlutoSDR 射频发射

RX端:
PlutoSDR 接收
  → 静默→有信号突发检测 (滑动窗功率)
  → 62.5kHz 捕获音 FFT 频偏估计 + 校正
  → 511-chip 同步序列相关 (精确帧同步)
  → 255-chip 周期导频跟踪 (相位/定时)
  → 127-chip Gold 码 DSSS 解扩
  → 去交织 + 软判决维特比译码
  → XOR 解白化 + CRC-32 验证
  → 按 file_id/seq 重组文件
```

## 快速开始

1. TX/RX 各自打开对应 .grc，修改 `device_uri` 为实际地址
2. 确保以下参数 TX 和 RX **完全一致**:
   - `center_freq` (2.45 GHz 起始)
   - `samp_rate` (1 MHz)
   - `code_length` (127)
   - `team_id` (0-9，比赛时每队不同)
   - `shared_key` (自己队伍的秘密密钥)
   - `hop_enabled` (1)
3. RX 先启动 (采集 30 秒)
4. TX 启动
5. RX 自动解码 → `decoded_file_XXXXXXXX.bin` + `rx_status.json`

## 参数调优

| 场景 | 建议 |
|---|---|
| 距离近/信号强 | `rx_gain=20 tx_attenuation=60` |
| 距离远/信号弱 | `rx_gain=50 tx_attenuation=30` |
| 干扰严重 | 增大 `code_length` (63→127→255), 开启 `hop_enabled` |
| 文件大 | `capture_seconds` 适当延长 |
