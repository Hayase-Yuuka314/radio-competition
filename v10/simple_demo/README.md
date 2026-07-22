# PlutoSDR 简单 2-FSK 文字收发学习 Demo

这是一个只用于学习的最小完整例子：TX 反复发送 `el psy kongroo`，RX 自动找到数据包、解调并把通过 CRC-32 校验的文本写入文件。

文件夹中真正运行只需要两份文件：

- `simple_fsk_tx_pluto.grc`：发射端；
- `simple_fsk_rx_pluto.grc`：接收端。

所有 Python 代码都已经嵌入 `.grc`，**没有 `demo_codec.py`，没有外部脚本路径问题**。

## 1. 工作原理

```text
el psy kongroo
  → 文本长度
  → CRC-32
  → 固定同步字
  → 2-FSK：0 使用 -75 kHz，1 使用 +75 kHz
  → PlutoSDR TX

PlutoSDR RX
  → 检测静默后的信号起点
  → 根据交替前导自动估计两个 FSK 频率和设备频偏
  → 检查同步字
  → 读取长度和文本
  → CRC-32 正确才写入文件
```

默认速率为 10 kbit/s；一个数据包共 248 bit，包含 64 bit 前导、32 bit 同步字、长度、14 字节文本和 CRC-32。每个包之前有 20 ms 静默，整个周期约 44.8 ms。

没有加密、FEC、DSSS、机器学习或比赛抗干扰策略。

## 2. 开源参考

设计时参考了以下公开项目/上游资料，但没有直接复制其流图代码：

- [ADI gr-iio / GNU Radio PlutoSDR 接口](https://github.com/analogdevicesinc/gr-iio)：使用标准 Pluto Source/Sink、URI、采样率、带宽和增益接口；
- [ADALM-Pluto-File-Transfer](https://github.com/patel999jay/ADALM-Pluto-File-Transfer)：参考其“先用 `iio_info` 找设备，再在 GRC 指定设备和输出文件”的基本流程；
- [GNU Radio issue #6575](https://github.com/gnuradio/gnuradio/issues/6575)：GNU Radio 3.10 的旧 Packet Header 块存在已知问题，因此本学习版使用非常小且直接可读的内嵌帧格式。

## 3. 当前已经完成的验证

本机使用：

```text
%RADIOCONDA%\python.exe
GNU Radio 3.10.12.0
%RADIOCONDA%\Library\bin\grcc.exe
```

已经通过：

- 两份 `.grc` 的 YAML 和 Embedded Python 语法检查；
- 两份 `.grc` 的真实 `grcc` 编译；
- GNU Radio TX/RX Embedded Python Block 实例化；
- 模拟加入 30 kHz 收发频偏和 12 dB SNR 噪声；
- RX 正确估计频偏、CRC-32 通过并逐字节恢复 `el psy kongroo`。

当前 `iio_info -S` 没有发现已连接的 Pluto context，因此最终射频实测仍需连接实际设备后完成。

## 4. 安全

1. 有线测试绝不能直接连接 TX 与 RX，必须串联合适的 30–60 dB 射频衰减器。
2. 无线测试前确认频率、功率、天线和地点符合当地规定。
3. `tx_attenuation_db` 是衰减量：`89.75` 最弱，`0` 最强。首次测试保持 `70 dB`，再逐步调整。
4. 搭线和拆线前停止 TX。

## 5. 查找 Pluto URI

连接设备后，在 PowerShell 执行：

```powershell
& "%RADIOCONDA%\Library\bin\iio_info.exe" -S
```

可能得到：

```text
ip:192.168.2.1
usb:3.8.5
```

把实际 URI 填入 TX/RX 流图的 `device_uri` 变量。两台 Pluto 连接同一电脑时，不要让两端误用同一个 URI。

## 6. 第一次运行

### 6.1 先启动 RX

```powershell
cd ".\simple_demo"
& "%RADIOCONDA%\Library\bin\gnuradio-companion.exe" simple_fsk_rx_pluto.grc
```

双击变量并确认：

| 变量 | 默认值 |
|---|---:|
| `device_uri` | 改为 RX Pluto 实际 URI |
| `center_frequency_hz` | `2450000000` |
| `samp_rate` | `1000000` |
| `samples_per_symbol` | `100` |
| `deviation_hz` | `75000` |
| `rx_gain_db` | `35` |
| `capture_seconds` | `15` |

点击 **Generate**，再点击 **Run**。终端应显示：

```text
[SIMPLE RX] Waiting for a 2-FSK text packet...
```

### 6.2 再启动 TX

```powershell
cd ".\simple_demo"
& "%RADIOCONDA%\Library\bin\gnuradio-companion.exe" simple_fsk_tx_pluto.grc
```

确认：

| 变量 | 默认值 |
|---|---:|
| `message` | `'el psy kongroo'` |
| `device_uri` | 改为 TX Pluto 实际 URI |
| `center_frequency_hz` | `2450000000` |
| `samp_rate` | `1000000` |
| `samples_per_symbol` | `100` |
| `deviation_hz` | `75000` |
| `tx_attenuation_db` | `70` |

点击 **Generate**，再点击 **Run**。TX 会不断重复发送，测试后手动停止。

## 7. 成功结果

RX 成功时终端显示：

```text
[SIMPLE RX] SUCCESS, CRC-32 passed
[SIMPLE RX] Message: el psy kongroo
[SIMPLE RX] Estimated CFO: ... Hz
```

运行目录生成：

- `received_text.txt`：内容必须为 `el psy kongroo`；
- `rx_status.json`：`status` 为 `SUCCESS`，`crc_ok` 为 `true`。

## 8. 修改输出路径

GRC 的变量值必须是合法 Python 字符串。推荐使用正斜杠和英文引号，例如：

```python
'D:/radio_test/received_text.txt'
```

状态文件：

```python
'D:/radio_test/rx_status.json'
```

不要写成没有引号的：

```text
D:\radio_test\received_text.txt
```

接收块会自动创建目标文件夹。

## 9. 修改发送内容

双击 TX 的 `message`，填写带英文引号的 Python 字符串：

```python
'hello pluto'
```

最长为 64 个 UTF-8 字节。TX/RX 不需要预先约定文本内容，RX 会从包中的长度字段读取。

## 10. 常见故障

| 现象 | 处理办法 |
|---|---|
| `No IIO context found` | 检查 Pluto 驱动、USB 线和供电，重新运行 `iio_info -S` |
| `Unable to create context` | `device_uri` 填错，重新复制扫描得到的完整 URI |
| RX 显示 `NO_VALID_PACKET` | 核对中心频率、采样率、每符号点数和频偏参数；确认 TX 已运行 |
| 信号太弱 | 在安全前提下把 TX 衰减从 70 调到 60/50，或提高 RX 增益 |
| 信号过强/CRC 失败 | 增大 TX 衰减、减小 RX 增益或拉开天线距离 |
| RX 很快退出 | 默认只采 15 秒，可把 `capture_seconds` 改为 30 |
| 输出路径语法错误 | 使用 `'D:/folder/file.txt'`，包含英文引号 |

## 11. 命令行编译检查

```powershell
cd ".\simple_demo"
& "%RADIOCONDA%\Library\bin\grcc.exe" simple_fsk_tx_pluto.grc
& "%RADIOCONDA%\Library\bin\grcc.exe" simple_fsk_rx_pluto.grc
```

会生成对应 Python 文件。由于两份 GRC 完全自包含，复制到其他电脑后不需要修改任何 `demo_codec.py` 路径。

