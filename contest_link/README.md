# Contest Data Link - QPSK 3MHz

## 文件

| 文件 | 用途 |
|---|---|
| `contest_data_tx.grc` | TX: 读文件→QPSK+RRC→PlutoSDR (2430-2435MHz, 接2.4G BPF) |
| `contest_data_rx.grc` | RX: PlutoSDR→QPSK解调→实时解码→文件重组 |

## 参数

| 参数 | 值 | 说明 |
|---|---|---|
| 采样率 | 3 MHz |  |
| sps | 2 | 1.5 Msps |
| 调制 | QPSK | 3 Mbps 原始速率 |
| 每包载荷 | 4096 字节 | 可调 |
| 前导 | 64 QPSK 符号 | PN 序列 |
| 同步字 | 0x1ACF | 16 bit |
| 帧头 | 64 bit | file_id+seq+total+payload_len |
| CRC | CRC-32 | 每包校验 |
| 输出 | `00-队名.txt` | 纯大写字母，无空格换行 |

## 吞吐

- 4096B/pkt: ~2.8 Mbps 净速率
- 100MB / 2.8Mbps ≈ 4.75 分钟 (在 5 分钟窗口内)

## 使用

1. TX端: 打开 `contest_data_tx.grc`, 修改 `device_uri` 为实际地址, `input_file` 为要发送的文件, Generate→Run
2. RX端: 打开 `contest_data_rx.grc`, 修改 `device_uri` 和 `team_name`, Generate→Run
3. RX 实时解码, 收到完整文件后自动输出 `00-队名.txt`
