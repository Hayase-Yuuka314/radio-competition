# PlutoSDR 简易 DSSS 文字收发 Demo 用户手册

这套 demo 会让发射端反复发送 UTF-8 文本 **`el psy kongroo`**，接收端自动寻找信号、纠正频偏、解扩和纠错，最后把通过 CRC-32 校验的明文写入 `decoded_message.txt`。

> 适用对象：第一次使用 GNU Radio Companion 和 PlutoSDR 的读者。按“第一次实际测试”逐项操作即可，不要求先懂通信原理。

## 1. 文件清单

| 文件 | 用途 |
|---|---|
| `demo_tx_pluto.grc` | PlutoSDR 发射端流图 |
| `demo_rx_pluto.grc` | PlutoSDR 接收端流图 |
| `demo_codec.py` | 两个流图共同使用的组包、扩频、同步、纠错和解码代码 |
| `self_test.py` | 不接硬件的离线验收测试 |
| `README.md` | 本手册 |

正常运行后还会生成：

| 输出文件 | 怎样判断 |
|---|---|
| `tx_manifest.json` | TX 实际文本、采样率、码长和波形长度记录；不记录共享密钥 |
| `decoded_message.txt` | 成功时内容应为 `el psy kongroo` |
| `rx_status.json` | 成功时 `status` 为 `SUCCESS`，`crc_ok` 为 `true` |

## 2. 这套流图到底做了什么

可以把它想成“把一张小纸条装进多层保护袋”：

```text
el psy kongroo
  ↓ 共享密钥 XOR 加扰（避免直接看到原文）
  ↓ CRC-32（判断收到的内容有没有损坏）
  ↓ K=7、1/2 码率卷积码（加入可用于纠错的冗余）
  ↓ 块交织（把连续干扰造成的错误打散）
  ↓ BPSK + 31 码片 DSSS 扩频（约 14.9 dB 理论处理增益）
  ↓ 捕获音、同步序列和周期导频（让两台不同步的 Pluto 能找到并跟踪包）
  ↓ PlutoSDR 发射

PlutoSDR 接收
  ↓ 找到“静默 → 有信号”的包头
  ↓ 用捕获音估计并校正载波频偏
  ↓ 用同步序列和周期导频校时、校相
  ↓ DSSS 解扩 → 去交织 → 软判决维特比译码
  ↓ 用同一共享密钥解扰 → CRC-32 验证
  ↓ el psy kongroo
```

它沿用了本工程的 DSSS 伪 Gold 扩频码、BPSK、卷积码、块交织、共享序列 XOR 加扰和 CRC 思路。与工程中只适合已知码片边界的 DSSS 仿真相比，这个 demo 额外加入了真实空口所需的突发检测、FFT 频偏估计和周期导频跟踪。

### “加密”一词必须说明白

这里实现的是**教学/测试用途的共享密钥 XOR 加扰（白化）**：TX 和 RX 用相同 `shared_key` 生成相同密钥流，异或两次后还原。密钥错误时，CRC 会拒绝输出。

它能证明“只有参数和共享密钥一致的接收端才能通过本 demo 的解码检查”，但它**不是经安全审计的现代端到端加密协议**，没有密钥协商、随机 nonce、身份认证和防重放能力。不要用它保护真实机密；正式系统应在本链路上层使用 AES-GCM、ChaCha20-Poly1305 等成熟认证加密协议。

## 3. 硬件和软件准备

### 3.1 推荐硬件

- 两台 ADALM-Pluto（最稳妥）：一台专做 TX，一台专做 RX；
- 两根适合测试频段的天线，或者一条射频同轴线；
- **有线测试必须串联总计 30–60 dB 的射频衰减器**；
- 两台电脑，或一台能同时稳定连接两台 Pluto 的电脑。

一台 Pluto 理论上支持全双工，但让两个独立 GNU Radio 进程同时打开同一个 IIO 设备，在不同系统/驱动组合下不一定稳定；本手册以“两台 Pluto”为标准方案。

### 3.2 软件

- GNU Radio 3.10；
- GNU Radio Companion；
- gr-iio / PlutoSDR Source 和 PlutoSDR Sink 块；
- libiio 命令行工具（至少要有 `iio_info`）；
- Python 3 和 NumPy。

Windows 用户可使用 GNU Radio 文档推荐的 RadioConda；GNU Radio 3.10 及以上已经把 gr-iio 放入 GNU Radio 基础安装。参考：[GNU Radio Windows 安装](https://wiki.gnuradio.org/index.php/WindowsInstall)、[ADI 的 GNU Radio / gr-iio 说明](https://wiki.analog.com/resources/tools-software/linux-software/gnuradio)。

如果 Windows 找不到 Pluto，请先安装 Pluto 驱动，再重新插拔设备；ADI 的排障页也建议以 `iio_info -s`/`-S` 检查连接：[PlutoSDR Troubleshooting](https://wiki.analog.com/university/tools/pluto/troubleshooting)。

### 3.3 本机已识别的实际 RadioConda 环境

本机不是“未安装 GNU Radio”的状态。已经实际识别并验证：

| 组件 | 本机路径/版本 |
|---|---|
| Python | `%RADIOCONDA%\python.exe`，Python 3.12.9 |
| GNU Radio | 3.10.12.0 |
| GNU Radio Companion | `%RADIOCONDA%\Library\bin\gnuradio-companion.exe` |
| GRC 编译器 | `%RADIOCONDA%\Library\bin\grcc.exe` |
| libiio 扫描工具 | `%RADIOCONDA%\Library\bin\iio_info.exe` |
| gr-iio Python 模块 | 已成功导入 `gnuradio.iio` |

后文优先给出这些绝对路径，因此不依赖 PowerShell 的 `PATH` 配置。2026-07-22 的只读设备扫描结果是 `No IIO context found`，表示软件已经存在，但扫描时没有发现已连接的 Pluto；接上设备后必须重新执行扫描。

## 4. 安全须知——先读再发射

1. **绝不能把 Pluto 的 TX 端口用同轴线直接接到 RX 端口。** 必须先核算并串联足够的射频衰减器，否则可能损坏接收端。
2. 无线发射前，确认中心频率、带宽、功率、天线和测试地点符合当地无线电法规及实验室规定。本文件中的 2.45 GHz 只是技术默认值，不是对任何地点的发射授权。
3. Pluto 的 TX 参数是“衰减量”：`89.75 dB` 最弱，数值越小，输出越强。首次测试从 `70 dB` 左右开始，逐步减小，绝不要一上来设为 `0 dB`。
4. 先用最小可用功率、近距离或屏蔽/有线环境测试。
5. 有线搭建或拆线前先停止 TX。

## 5. 第一次实际测试（一步一步照做）

### 第一步：连接并确认 Pluto

把 Pluto 接到电脑。在 **RadioConda Prompt** 或安装了 libiio 的终端输入：

```powershell
& "%RADIOCONDA%\Library\bin\iio_info.exe" -S
```

旧版 libiio 也可能使用小写 `-s`：

```powershell
& "%RADIOCONDA%\Library\bin\iio_info.exe" -s
```

记下每台设备显示的 URI，例如：

```text
ip:192.168.2.1
usb:3.8.5
```

然后单独验证：

```powershell
& "%RADIOCONDA%\Library\bin\iio_info.exe" -u ip:192.168.2.1
```

能列出 `ad9361-phy`、接收和发射数据通道，才算连接正常。`iio_info -S` 用来扫描 context、`-u` 用来指定 URI，这是 libiio 的标准用法：[iio_info 文档](https://analogdevicesinc.github.io/libiio/main/tools/iio_info.html)。

### 第二步：先跑不发射的离线测试

在 RadioConda Prompt 进入本文件夹：

```powershell
cd ".\demo"
& "%RADIOCONDA%\python.exe" -B self_test.py
```

最后应看到：

```text
ALL OFFLINE DEMO TESTS PASSED
```

该测试会加入约 18 kHz 频偏、5 dB SNR 噪声、连续窄带干扰和 100 ppm 采样钟误差，然后检查原文、错误密钥拒绝、流式输入及两个 `.grc` 文件的结构。它不发射射频。

### 第三步：打开 RX 流图并改 URI

仍在 `demo` 文件夹运行：

```powershell
& "%RADIOCONDA%\Library\bin\gnuradio-companion.exe" demo_rx_pluto.grc
```

在画布上双击变量 `device_uri`，改成 RX 那台 Pluto 的实际 URI。

先保持这些默认值不变：

| RX 变量 | 默认值 |
|---|---:|
| `center_frequency_hz` | `2450000000` |
| `samp_rate` | `1000000` |
| `rf_bandwidth_hz` | `800000` |
| `samples_per_chip` | `4` |
| `code_length` | `31` |
| `team_id` | `0` |
| `shared_key` | `demo-shared-key-2026` |
| Pluto Source 的 Gain Mode | `manual`（已固定） |
| `rx_gain_db` | `35` |
| `capture_seconds` | `15` |

点击工具栏的 **Generate**，确认没有红色错误，然后点击 **Run**。终端应显示：

```text
[DEMO RX] Waiting for a protected DSSS packet...
```

RX 只采集 15 秒，之后自动结束；来不及启动 TX 时，再点一次 Run 即可。

### 第四步：打开 TX 流图并改 URI

在 TX 电脑的 RadioConda Prompt 进入同一份 `demo` 文件夹并运行：

```powershell
& "%RADIOCONDA%\Library\bin\gnuradio-companion.exe" demo_tx_pluto.grc
```

双击 `device_uri`，改为 TX Pluto 的实际 URI。确认 `message` 是：

```python
'el psy kongroo'
```

TX 与 RX 的以下参数必须逐字一致：

- `center_frequency_hz`
- `samp_rate`
- `samples_per_chip`
- `code_length`
- `team_id`
- `shared_key`

第一次把 `tx_attenuation_db` 设为 `70.0`。点击 **Generate**，再点击 **Run**。终端应显示：

```text
[DEMO TX] Repeating protected message: el psy kongroo
```

TX 会反复发送同一个约 84.7 ms 的测试周期，直到手动停止。测试完成后点 **Stop**。

### 第五步：看 RX 结果

成功时 RX 终端会显示类似：

```text
[DEMO RX] SUCCESS, CRC-32 passed
[DEMO RX] Message: el psy kongroo
[DEMO RX] CFO: 12345.6 Hz, sync: 0.8xx, weakest pilot: 0.8xx
```

并在运行目录生成：

```text
decoded_message.txt
rx_status.json
```

打开 `decoded_message.txt`，内容应严格等于：

```text
el psy kongroo
```

只有同时满足“终端显示 SUCCESS、文本完全相同、`crc_ok=true`”才算测试通过。

## 6. 无线和有线两种接法

### A. 近距离无线测试

1. 两台 Pluto 分别接合适的天线；
2. 相距约 1–3 米，避免天线端口贴在一起；
3. TX 衰减先用 `70 dB`，RX 增益先用 `35 dB`；
4. 收不到时依次尝试 TX 衰减 `60 dB`、`50 dB`，每次只改一项；
5. 若信号太强导致失真，增大 TX 衰减或减小 `rx_gain_db`。

### B. 同轴有线测试

接法：

```text
TX Pluto 的 TX 口 ── 同轴线 ── 30–60 dB 总衰减 ── RX Pluto 的 RX 口
```

先确认衰减器在 2.45 GHz 的额定功率、阻抗和衰减值都合适。初次仍以 `tx_attenuation_db=70` 开始；信号不足时逐步减小。**没有合适衰减器就不要做有线直连。**

## 7. 参数怎么改

### 改发送文字

双击 TX 的 `message`。本 demo 单包最多 **16 个 UTF-8 字节**。英文字母通常一字节；一个常用汉字通常占三字节。因此默认的 `el psy kongroo` 可以发送，但较长中文不能直接塞入这个简化包。

改完后重新 Generate 和 Run。

### 改共享密钥

同时修改 TX 和 RX 的 `shared_key`。两边不一致时应解码失败，这是预期行为。不要把本 demo 的默认密钥用于真实数据。

### 改频率

同时改 TX/RX 的 `center_frequency_hz`，并确认频段、天线、滤波器和发射权限。两个值差几 kHz 并不等同于合法地“自动找台”；这里只能校正设备振荡器造成的有限频偏，不能代替正确配置中心频率。

### 改抗干扰强度

`code_length=31` 的理论 DSSS 处理增益约为：

```text
10 × log10(31) ≈ 14.9 dB
```

码长越长，抗窄带干扰能力一般越强，但占用的码片和发送时间也越多。当前包格式、同步和 CPU 负担针对 `31` 做了实际离线验收；初次硬件测试不要改。

## 8. 常见故障排查

| 现象 | 最可能原因 | 处理办法 |
|---|---|---|
| GRC 中 Pluto 块变红/显示 unknown block | 缺少 gr-iio | 使用含 gr-iio 的 GNU Radio 3.10 环境；从 RadioConda Prompt 启动 GRC |
| `Unable to create context` / `No such device` | URI 错误、驱动或 USB 问题 | 重新运行 `iio_info -S`，把完整 URI 写入 `device_uri` |
| `ModuleNotFoundError: demo_codec` | 不是从 `demo` 文件夹生成/运行 | 在 RadioConda Prompt 先 `cd ...\demo`，再启动 GRC |
| RX 始终 `NO_VALID_PACKET` | TX 未运行或参数不一致 | 逐项核对频率、采样率、码长、team_id、shared_key |
| 能看到信号但 CRC 失败 | 共享密钥不同、削顶、误码过多 | 先核对密钥；增大 TX 衰减或减小 RX 增益防止过载 |
| 完全收不到 | 功率太小、天线/端口接错 | 确认 TX/RX 端口；在安全前提下把 TX 衰减从 70 逐步减到 60/50 |
| 时好时坏 | USB 丢样、CPU 忙或信号临界 | 关闭占 CPU 的程序，换 USB 口/线，保持 1 MS/s，延长 `capture_seconds` |
| RX 很快结束 | 默认只采 15 秒 | 先运行 TX，或把 `capture_seconds` 改为 30 |
| 输出文件不知在哪里 | GRC 的工作目录不同 | 从 `demo` 目录启动 GRC；也可把输出变量改为绝对路径 |

建议一次只改一个参数，并保存每次的 `rx_status.json`。`sync_score` 和 `minimum_pilot_score` 越接近 1 通常越好；有 CRC 通过时，以 CRC 结果为最终依据。

## 9. 不打开 GRC，直接生成和运行

在能够识别 Pluto 块的 RadioConda Prompt 中：

```powershell
cd ".\demo"
& "%RADIOCONDA%\Library\bin\grcc.exe" demo_tx_pluto.grc
& "%RADIOCONDA%\Library\bin\grcc.exe" demo_rx_pluto.grc
```

这会生成 `demo_tx_pluto.py` 和 `demo_rx_pluto.py`。在 RX 电脑先运行：

```powershell
& "%RADIOCONDA%\python.exe" -u demo_rx_pluto.py
```

再在 TX 电脑运行：

```powershell
& "%RADIOCONDA%\python.exe" -u demo_tx_pluto.py
```

注意：命令行运行前仍要先在 `.grc` 中填好正确 URI 并重新 `grcc`，或者编辑生成脚本中的变量。优先推荐在 GRC 中修改变量。

## 10. 验收记录与已知边界

本文件夹创建时已经在当前工程的 Python 环境完成以下自动测试：

- 两份 GRC 的 YAML 可解析；
- 两个 Embedded Python Block 的源码可编译；
- 默认文本能够完整组包并严格还原；
- 在约 18 kHz 频偏、5 dB SNR、连续窄带干扰和 100 ppm 采样钟误差下成功恢复 `el psy kongroo`；
- 错误共享密钥无法通过 CRC；
- GNU Radio 风格的分块流式输入能生成正确的文本和 JSON 输出。

当前电脑已经用 `%RADIOCONDA%` 中的 GNU Radio 3.10.12.0 完成两份 `.grc` 的真实 `grcc` 编译，并在 GNU Radio 运行时中实例化 TX/RX Embedded Python Block、分块送入受损 IQ、成功恢复原文。但 `iio_info -S` 扫描时返回 `No IIO context found`，所以还没有可供本任务使用的实际 Pluto context，不能伪称已经完成射频收发。接上 Pluto 后仍需按第 5 节完成最终硬件验收。

这个 demo 的边界：

- 单包只支持 16 字节；
- 重复发送固定测试消息，没有 ACK、重传协议或多用户接入；
- 共享密钥加扰不是正式安全加密；
- 默认矩形码片和固定参数以清楚、容易排障为优先，不追求频谱效率；
- 理论处理增益不等于在所有真实干扰、衰落和过载场景中都能获得同样提升。

## 11. 最短操作卡

```text
1. 有线必须加 30–60 dB 衰减；无线先确认法规。
2. 用 `%RADIOCONDA%\Library\bin\iio_info.exe -S` 分别记下 TX/RX URI。
3. `cd demo`；用 `%RADIOCONDA%\python.exe -B self_test.py`，看到 ALL ... PASSED。
4. RX：打开 demo_rx_pluto.grc → 改 URI → Generate → Run。
5. TX：打开 demo_tx_pluto.grc → 改 URI → 衰减先 70 dB → Generate → Run。
6. RX 出现 SUCCESS 后查看 decoded_message.txt。
7. 内容必须是 el psy kongroo，rx_status.json 必须 crc_ok=true。
8. 停止 TX。
```
