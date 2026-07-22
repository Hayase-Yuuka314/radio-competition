# GNU Radio 竞赛文件链路（单 `.grc`）

主工程是 [`sdr_contest_complete.grc`](sdr_contest_complete.grc)。协议、收发、信道、IQ 回放和 Pluto/NanoSDR 接口都保存在这一份 GRC 中；自定义逻辑使用 Embedded Python Block，不需要额外 OOT 模块。

## 已实现的数据链

```text
文件 -> 256 B 分块/序号 -> 14 B 强健帧头+CRC16
     -> payload CRC32 -> 可选 K=7 rate-1/2 卷积码
     -> BPSK/QPSK -> RRC -> 有限 IQ 流
     -> AWGN/CFO/SRO/多径 + 单音/突发/IQ/DC/削顶
     -> 前导检测/定时/CFO/Costas -> FEC/CRC
     -> 去重/重排 -> 完整后原子写出文件
```

接收端按失败阶段分别统计检测、帧头、payload CRC、重复帧和缺块。CRC 未通过的块绝不会进入最终文件；没有收齐时只保存独立的 `decoded_payload.bin.parts/block_*.bin`，不会猜测或修补评分文件。

支持四种角色：

- `sim`：默认模式，发送文件经过可复现信道后回环接收。
- `replay`：读取 `complex64` IQ 文件，走相同的连续接收链。
- `tx`：通过 pyadi-iio 向指定 Pluto/NanoSDR 做有限、非 cyclic 发送。
- `rx`：通过 pyadi-iio 做有限时长只读采集并解码。

## 环境与运行

本机当前终端没有激活 GNU Radio。请从 RadioConda Prompt 运行：

```powershell
cd C:\Users\16839\Desktop\无线电gpt
python -m pip install -e .
cd gnu_radio_contest_grc
gnuradio-companion sdr_contest_complete.grc
```

在 GRC 中先保持 `role = 'sim'`，点击 Generate，再 Run。默认输入是 `input_payload.bin`。成功后应得到：

- `decoded_payload.bin`：逐字节恢复文件；
- `tx_manifest.json`：输入 SHA-256、帧数、帧长和 PHY 参数；
- `run_metrics.json`：分类计数、缺块、输出 SHA-256、`byte_exact`；
- `rx_capture.c64`：接收端 complex64 原始 IQ；
- `rx_device_manifest.json`：回放或硬件采集参数与硬件读回值。

命令行生成/运行也可以使用：

```powershell
grcc sdr_contest_complete.grc
python -u sdr_contest_complete.py
```

如 GRC 报 Embedded Python Block 无法导入 `wireless_competition`，说明启动 GRC 的 RadioConda 环境还没有执行仓库根目录的 `python -m pip install -e .`。

## 常用参数

| 参数 | 说明 | 默认值 |
|---|---|---:|
| `modulation` | `bpsk` 或 `qpsk` | `bpsk` |
| `fec_mode` | `none` 或 `convolutional` | `convolutional` |
| `samp_rate` | 复基带采样率 | 2 MS/s |
| `samples_per_symbol` | RRC 过采样倍数 | 8 |
| `snr_db` | 仿真 SNR | 30 dB |
| `cfo_hz` | 载波频偏 | 0 Hz |
| `sro_ppm` | 收发采样钟差 | 0 ppm |
| `channel_taps` | 复数多径 FIR | `[1+0j]` |
| `tone_inr_db` | 单音干扰 INR；≤-100 关闭 | -120 dB |
| `burst_probability` | 每样本突发概率 | 0 |
| `clipping_threshold` | 幅度限幅；≤0 关闭 | 0.95 |

协议 v1 的前导固定为 64 符号。保护间隔可以调整；仓库接收器已修复为实际使用 GRC 传入的 `guard_symbols`。

## IQ 回放

1. 把 `role` 改为 `replay`。
2. 将 `replay_path` 指向 `complex64 little-endian` 文件。
3. 保证 `samp_rate`、调制、FEC、RRC 和发送端一致。
4. 运行后查看 `run_metrics.json`。

回放流没有 GNU Radio 帧长 tag，接收块会自动切换到脉冲成形前导相关搜索。读取量受 `max_capture_samples` 硬限制。

## Pluto/NanoSDR 只接收

把 `role` 改为 `rx`，显式填写：

- `device_uri`；
- `center_frequency_hz`；
- `rf_bandwidth_hz`、`rx_gain_mode`/`rx_gain_db`；
- 有限的 `rf_duration_s`。

RX 是只读路径，不要求打开 TX 安全门。先用 `iio_info -s` 发现并记录精确 URI；两台设备同时可见时不要依赖枚举顺序。

## 真实发射安全门

默认配置无法发射。只有下面条件全部满足，TX block 才会导入 `adi` 并打开设备：

1. `role == 'tx'`；
2. `rf_enable == True`；
3. `rules_confirmed == True`；
4. `physical_path_confirmed == True`；
5. `contest_rules.yaml` 中 `rules.confirmed: true`；
6. 中心频率明确落在规则列出的中心频率或频段内；
7. 带宽和有限发送时长不超过规则上限。

TX 始终设置 `tx_cyclic_buffer = False`，并在 `stop()` 的 `finally` 路径销毁 TX buffer。AD936x 的 `tx_attenuation_db=-89.75` 是最低输出；不要把它误当作正增益。

有线测试前必须计算 TX 输出、衰减器和接收最大安全输入，禁止不经核算把 TX 直接接到 RX。OTA 前还要核对正确频段的滤波器/天线以及本地许可和正式赛规。

## 验证边界

仓库自动测试会验证：GRC YAML/连接完整、五个嵌入块可编译、BPSK/QPSK 与 FEC 的端到端逐字节恢复，以及默认 TX 安全门拒绝发射。当前机器没有 GNU Radio、gr-iio、pyadi-iio 和连接的 NanoSDR，因此 `grcc` 生成、GRC GUI 加载及硬件在环仍必须在 RadioConda/实机环境复验，不能用静态测试冒充实机证据。
