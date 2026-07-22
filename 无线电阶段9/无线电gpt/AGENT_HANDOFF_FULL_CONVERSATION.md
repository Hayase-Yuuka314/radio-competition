# GNU Radio / PlutoSDR 项目完整对话与 Agent 交接记录

> 生成日期：2026-07-22（Asia/Shanghai）  
> 工作区：`C:\Users\16839\Desktop\无线电gpt`  
> 用途：供后续 Agent 在不依赖本次聊天上下文的情况下继续检测、修改、验证和实机联调。

## 0. 导出范围与边界

本文件包含：

- 当前上下文中能够恢复的用户输入、助手最终回复和关键工作进度；
- 使用过的本机工具/API、命令、skill 和重要返回结果；
- 当前工程文件、GNU Radio/RadioConda/PlutoSDR 状态；
- TX/RX GRC 架构、安全门、输出文件和测试结果；
- 需要向主办方确认的参数；
- 后续 Agent 建议采用的检查顺序、决策依据和风险边界。

本文件不包含系统/开发者隐藏指令、认证信息或模型私有逐 token 思维链。下文的“思考方向”是可审计的工程决策框架、证据、假设和取舍，不是隐藏推理记录。

由于对话在长任务中发生过上下文压缩，最早一次“使用一个 `.grc` 搭建完整工程”的助手逐字回复已经不在当前可恢复上下文中；该部分以工作区文件、测试和后续对话证据重建。其余当前可见的关键用户输入和助手答复均记录如下。

---

## 1. 当前结论（后续 Agent 先读这里）

### 1.1 软件环境

| 项目 | 当前状态 |
|---|---|
| RadioConda | 安装在 `E:\radioconda` |
| RadioConda Python | 3.12.9 |
| GNU Radio | 3.10.12.0 |
| GNU Radio Companion | `E:\radioconda\Scripts\gnuradio-companion.exe` |
| `grcc` | `E:\radioconda\Library\bin\grcc.exe`，可用 |
| RadioConda `pyadi-iio` | 0.0.19，可导入 |
| RadioConda `pylibiio` | 0.26，可导入 |
| 系统 Python | `C:\Users\16839\AppData\Local\Programs\Python\Python312\python.exe`，3.12.6 |
| 系统 Python `pyadi-iio` | 0.0.21；默认缺少原生 libiio DLL 搜索路径，直接 `import adi` 会失败 |
| 系统 Python `pylibiio` | 0.25 |

RadioConda 没有加入普通 PowerShell 的默认 `PATH`。需要从 RadioConda Prompt 启动，或者在进程内加入：

```powershell
$env:PATH = 'E:\radioconda;E:\radioconda\Library\mingw-w64\bin;E:\radioconda\Library\usr\bin;E:\radioconda\Library\bin;E:\radioconda\Scripts;' + $env:PATH
$env:CONDA_PREFIX = 'E:\radioconda'
```

### 1.2 PlutoSDR/NanoSDR 当前状态

最初 Windows 只能枚举 USB 父设备，libiio 扫描不到 context；在后续用户再次运行时，USB IIO 已恢复正常。最近一次只读检测结果为：

```text
设备：Analog Devices Inc. PlutoSDR (ADALM-PLUTO)
USB VID:PID：0456:b673
序列号：03df6d6e33072e162fd765663b1f360e37
USB URI：usb:1.3.5
硬件模型：Analog Devices PlutoSDR Rev.B (Z7010-AD9363A)
固件：v0.39-dirty
libiio：0.26
IIO devices：ad9361-phy、xadc、cf-ad9361-dds-core-lpc、cf-ad9361-lpc
```

最近一次验证：

```powershell
iio_info -S usb
```

成功返回：

```text
Available contexts:
0: 0456:b673 (Analog Devices Inc. PlutoSDR (ADALM-PLUTO)),
serial=03df6d6e33072e162fd765663b1f360e37 [usb:1.3.5]
```

直接执行 `iio_info -u usb:` 也成功创建 context。IP 后端仍不可用：

```text
ip:192.168.2.1 -> timeout / error 10060
```

因此当前 GRC 的最大直接问题是：TX/RX 两份 `.grc` 中的 `device_uri` 仍保存为 `'ip:192.168.2.1'`，应该改成当前实际 URI `'usb:1.3.5'`，或者只有一台设备时使用 `'usb:'`。USB 总线路径在拔插后可能变化，应再次运行 `iio_info -S usb`。

### 1.3 当前工程入口

| 文件 | 用途 |
|---|---|
| `gnu_radio_contest_grc/sdr_contest_complete.grc` | 旧的组合图：仿真、IQ 回放、协议回归、旧 pyadi 硬件接口 |
| `gnu_radio_contest_grc/sdr_contest_tx_pluto.grc` | 独立真实 TX 图，使用原生 `PlutoSDR Sink` |
| `gnu_radio_contest_grc/sdr_contest_rx_pluto.grc` | 独立真实 RX 图，使用原生 `PlutoSDR Source` |
| `gnu_radio_contest_grc/build_split_grc.py` | 从组合图中的已测试 Embedded Python PHY 生成拆分 TX/RX GRC |
| `gnu_radio_contest_grc/contest_rules.yaml` | TX 发射安全门的赛规约束 |
| `gnu_radio_contest_grc/README.md` | 使用说明 |

重要维护规则：`build_split_grc.py` 内含 TX/RX 默认值。若只在 GRC GUI 中改 `.grc`，之后再次运行生成器可能覆盖手工修改。长期修改应同步改生成器，再重新生成并执行 `grcc`。

### 1.4 当前 GRC 参数（2026-07-22 读取）

TX：

```text
device_uri='ip:192.168.2.1'
center_frequency_hz=2400000000
samp_rate=2000000
rf_bandwidth_hz=1000000
rf_duration_s=5.0
tx_attenuation_db=89.75
rf_enable=False
rules_confirmed=False
physical_path_confirmed=False
input_mode='placeholder'
input_path='input_payload.bin'
```

RX：

```text
device_uri='ip:192.168.2.1'
center_frequency_hz=2400000000
samp_rate=2000000
rf_bandwidth_hz=1000000
rf_duration_s=5.0
rx_gain_mode='manual'
rx_gain_db=30.0
output_path='decoded_payload.bin'
metrics_path='run_metrics.json'
iq_capture_path='rx_capture.c64'
```

`2400000000` 只是可通过 GRC 参数范围校验的示例值，不代表已获比赛或当地法规授权。

### 1.5 当前赛规文件状态

`gnu_radio_contest_grc/contest_rules.yaml` 当前为：

```yaml
rules:
  confirmed: false
  contest_duration_s: null
  scoring_mode: null

rf:
  allowed_bands_hz: null
  allowed_center_frequencies_hz: null
  max_occupied_bandwidth_hz: null
  max_tx_power_dbm: null
  max_tx_gain_db: null

hardware:
  device_model: NanoSDR_Pluto_compatible
  tx_uri: null
  rx_uri: null
```

这意味着 TX 必须继续 fail-closed。不得为了消除报错而猜测频率、带宽、功率或比赛时长。

### 1.6 自动测试状态

拆分完成后执行过：

```powershell
python -m pytest -q
```

结果：

```text
145 passed in 21.04s
```

2026-07-22 本文件生成前重新进行只收集检查：

```text
145 tests collected
```

执行过的其他验证：

- 两份 `.grc` 均由 GNU Radio 3.10.12.0 的 `grcc` 成功生成 Python；
- 生成模块在 RadioConda 中导入成功；
- 生成代码确认构造 `iio.fmcomms2_sink_fc32` 和 `iio.fmcomms2_source_fc32`；
- 新拆分 TX Embedded PHY 与 RX Embedded PHY 逐字节恢复通过；
- 默认 TX 在构造 Pluto Sink 前抛出 `RF TX gate closed`，证明默认不会进入发射硬件初始化；
- 尚未完成经过授权的真实 RF TX/RX 端到端测试。

---

## 2. 使用过的 skill、API 与本机工具

### 2.1 使用的本地 skill

名称：`run-sdr-contest-stack`  
路径：`C:\Users\16839\Desktop\无线电gpt\run-sdr-contest-stack\SKILL.md`

核心规则摘要：

1. 先获取完整比赛合同：频段、带宽、功率、时长、评分、反馈、换频和波形许可。
2. RadioConda 只是环境；Pluto API 优先级为：短脚本用 pyadi-iio，完整实时流用 GNU Radio + gr-iio，诊断用 libiio。
3. 实施顺序：文件/数组协议 → 信道仿真 → IQ 回放 → 有衰减的有线/屏蔽测试 → 获授权 OTA。
4. TX 必须在规则和物理路径确认后才能运行；cyclic 必须有停止与清理路径。
5. TX/RX 应可独立启动，不能依赖比赛期间的非 SDR 侧信道。
6. 保留原始输入和输出，不得“修复”评分文件；记录哈希、帧、CRC、缺块和重复帧。
7. 两台设备可见时必须绑定 URI/序列号，不依赖“第一台设备”。

读取过的参考：

- `run-sdr-contest-stack/references/pluto-api-patterns.md`
- `run-sdr-contest-stack/references/competition-workflow.md`

### 2.2 使用过的 Codex 工具/API

| 工具/API | 用途 |
|---|---|
| `functions.exec` | 编排 PowerShell、本机命令和补丁调用 |
| `shell_command` | 只读检测、运行 grcc、pytest、libiio 和 PowerShell 设备查询 |
| `apply_patch` | 新增/修改工程源文件、测试和文档 |
| `wait` | 等待长时间 pytest/设备扫描命令 |

未使用：Web 搜索、浏览器、邮件/日历/云盘连接器、图像生成、子 Agent。没有对外发送消息，没有联网安装插件。

### 2.3 重要本机命令

软件/硬件探测：

```powershell
python run-sdr-contest-stack\scripts\probe_sdr_stack.py --versions --hardware --json -
```

GNU Radio 版本：

```powershell
E:\radioconda\Library\bin\gnuradio-config-info.exe --version
```

GRC 编译：

```powershell
E:\radioconda\Library\bin\grcc.exe -o gnu_radio_contest_grc `
  gnu_radio_contest_grc\sdr_contest_tx_pluto.grc `
  gnu_radio_contest_grc\sdr_contest_rx_pluto.grc
```

IIO 发现：

```powershell
iio_info -S usb
iio_info -S ip
iio_info -T 1000 -u usb:
iio_info -T 1000 -u ip:192.168.2.1
```

测试：

```powershell
python -m pytest tests\integration\test_grc_project.py -q
python -m pytest -q
```

Windows 设备诊断使用过：

```powershell
Get-PnpDevice -PresentOnly
Get-PnpDeviceProperty
Get-NetAdapter -IncludeHidden
Get-NetIPAddress -AddressFamily IPv4
Get-NetNeighbor
Get-Volume
Get-CimInstance Win32_SerialPort
Test-Connection 192.168.2.1
```

---

## 3. 工程架构和决策依据

### 3.1 为什么拆成两个 GRC

比赛场景预期 TX、RX 位于不同电脑、不同 SDR，且不能依靠 Wi-Fi、网线、串口等侧信道。独立 GRC 可以单独重启、配置 URI、保存日志，符合比赛部署方式。

### 3.2 TX 图结构

```text
默认占位复正弦 ─┐
                 ├─ Selector ─ Head(有限样本) ─ TX 授权阀 ─ PlutoSDR Sink
竞赛文件协议源 ─┘
```

关键点：

- `input_mode='placeholder'`：默认 100 kHz、幅度 0.10 的复基带正弦；
- `input_mode='contest_file'`：读取 `input_path`，使用原有分块、帧头、CRC、卷积 FEC、BPSK/QPSK、RRC；
- `Head` 限制 `max_tx_samples=min(int(rf_duration_s*samp_rate), 10000000)`；
- Pluto Sink 使用原生 `iio_pluto_sink`，生成 `iio.fmcomms2_sink_fc32`；
- `cyclic=False`；
- `tx_attenuation_db=89.75` 是原生 Pluto GRC 块的正衰减值，表示最低输出，不应写成 `-89.75`；
- 初始化前置 Python Snippet 在构造 Pluto Sink 前校验规则；流内授权阀在调度启动时再次校验。

TX 安全门要求同时满足：

```text
GRC: rf_enable == True
GRC: rules_confirmed == True
GRC: physical_path_confirmed == True
YAML: rules.confirmed == true
中心频率明确落入 allowed_center_frequencies_hz 或 allowed_bands_hz
rf_bandwidth_hz <= max_occupied_bandwidth_hz
rf_duration_s <= contest_duration_s
0 <= tx_attenuation_db <= 89.75
```

### 3.3 RX 图结构

```text
PlutoSDR Source ─ Head(有限采集) ─┬─ 原始 IQ File Sink
                                  └─ 同步/解调/FEC/CRC/去重/重组 Sink
```

关键点：

- 使用原生 `iio_pluto_source`，生成 `iio.fmcomms2_source_fc32`；
- `Head` 限制采集时长和最大样本数；
- 连续硬件 IQ 没有仿真帧 tag，因此 `use_frame_tags=False`，接收器通过前导相关搜索；
- CRC 未通过的数据不会进入最终文件；
- 不完整时只保存已验证的分块，不猜测缺失内容。

### 3.4 为什么拆分图不含信道模拟

用户明确要求中间信号模拟可以省略，真实 TX/RX 直接通过各自 Pluto 块工作。旧组合图继续保留 AWGN、CFO、SRO、多径、单音/突发干扰和 IQ 回放，用于离线回归。

### 3.5 RX 输出

默认工作目录通常是：

```text
C:\Users\16839\Desktop\无线电gpt\gnu_radio_contest_grc
```

输出：

| 文件 | 含义 |
|---|---|
| `decoded_payload.bin` | 全部数据块齐全且 CRC 通过后的最终二进制文件 |
| `run_metrics.json` | 检测、帧头、CRC、重复、缺块、哈希等指标 |
| `rx_capture.c64` | complex64 little-endian 原始 IQ |
| `decoded_payload.bin.parts/block_*.bin` | 接收不完整时保存的已验证分块 |

这些文件通常在有限采集结束或点击 Stop 后完成最终扫描和写入。若 Pluto Source 在构造 context 时失败，本次运行不会更新任何输出。

查看方法：

```powershell
Get-Item .\decoded_payload.bin
Get-FileHash .\decoded_payload.bin -Algorithm SHA256
Format-Hex .\decoded_payload.bin | Select-Object -First 20

Get-Content .\run_metrics.json -Raw | ConvertFrom-Json | Format-List
```

IQ 快速查看示例：

```python
import numpy as np
import matplotlib.pyplot as plt

iq = np.fromfile("rx_capture.c64", dtype=np.complex64)
print("samples", len(iq))
print("peak", np.max(np.abs(iq)))
print("mean power", np.mean(np.abs(iq) ** 2))
plt.psd(iq[:min(len(iq), 1_000_000)], NFFT=4096, Fs=2_000_000)
plt.show()
```

---

## 4. 按时间顺序的对话记录

### 阶段 A：最初工程请求（上下文压缩后重建）

**用户：**

> 读取其中的skill，用一个.grc文件来搭建这个工程项目。确保一切功能完整。将文件新建一个文件夹来保存

**助手完成的工作（根据工作区和后续测试重建）：**

- 读取 `run-sdr-contest-stack/SKILL.md`；
- 创建 `gnu_radio_contest_grc/`；
- 创建组合工程 `sdr_contest_complete.grc`；
- 嵌入文件分块、序号、帧头、CRC、卷积码、BPSK/QPSK、RRC、同步、去重、重组；
- 加入仿真信道、干扰、IQ 回放和受控 Pluto/NanoSDR pyadi 接口；
- 创建 README、自定义块源、测试；
- 初始默认模式为仿真，RF TX fail-closed。

最早的助手逐字最终回复已不在可恢复上下文中，应以当前文件和测试为准。

### 阶段 B：检测本机软件和硬件

**用户：**

> 检测本机中的GNU Radio、grcc、pyadi-iio 和 NanoSDR。

**助手关键进度输出：**

> 我会做全程只读检测：先检查当前终端的 GNU Radio/grcc、pyadi-iio/libiio，再枚举 Windows 中可能未加入 PATH 的 RadioConda/Python 环境，最后检查 USB、网络适配器与 IIO/Soapy 发现结果来判断 NanoSDR 是否实际连接。不会启动任何发射。

> 第一轮结果已明确：当前终端的 Python 3.12 环境中已安装 `pyadi-iio 0.0.21` 和 `pylibiio 0.25`；但当前 `PATH` 下没有发现 GNU Radio、GNU Radio Companion 或 `grcc`。我正在继续排查未加入 PATH 的 RadioConda/独立安装，并用 USB、网卡和 libiio 做 NanoSDR 实机发现。

> 发现了两个关键点：系统注册表中同时存在 RadioConda 2021 和 2025 的安装记录，而且开始菜单里有 GNU Radio Companion 快捷方式，因此 GNU Radio 很可能只是未加入当前终端的 `PATH`。USB 设备也已识别到 `PlutoSDR (ADALM-PLUTO)`，序列号为 `03DF…F360E37`；不过它没有建立 `192.168.2.x` 网卡连接。

> RadioConda 的有效安装目录已定位到 `E:\radioconda`，其中 GNU Radio Companion、GNU Radio 配置工具、libiio 工具和 SoapySDR 工具都实际存在。当前系统 Python 的问题也已定位：只装了 Python 包，但找不到原生 `libiio` 动态库，所以 `import iio` 和 `import adi` 均会失败；我现在改用完整的 RadioConda 环境核验版本、`grcc` 命令和硬件发现能力。

> 目前可以把 NanoSDR 的状态定为“硬件已枚举，但还不可用于 IIO 流”：Windows USB 层显示设备正常、无错误码，但 libiio 的 USB 扫描没有找到上下文，系统也没有出现 Pluto 的串口、磁盘或 RNDIS 网卡接口。

**助手最终回复：**

> 检测完成，全程只读，未修改系统或启动发射。
>
> | 项目 | 检测结果 |
> |---|---|
> | GNU Radio | 已安装，版本 `3.10.12.0`，位于 `E:\radioconda`，但未加入当前终端的 `PATH` |
> | GNU Radio Companion | 已安装，程序为 `E:\radioconda\Scripts\gnuradio-companion.exe` |
> | grcc | 已安装，位于 `E:\radioconda\Library\bin\grcc.exe`；帮助命令运行正常 |
> | pyadi-iio | RadioConda 中为 `0.0.19`，可正常导入；系统 Python 中为 `0.0.21`，默认缺少 `libiio.dll` 搜索路径 |
> | pylibiio | RadioConda 中为 `0.26`，工作正常；系统 Python 中为 `0.25` |
> | NanoSDR | USB 层已识别为 `PlutoSDR (ADALM-PLUTO)`，但当时无法建立 IIO 上下文，暂不能正常收发数据 |
>
> NanoSDR 的 USB 信息：VID/PID `0456:B673`，序列号 `03DF6D6E33072E162FD765663B1F360E37`，Windows 状态 OK。建议使用 RadioConda Prompt，并修复完整 USB 驱动；验收标准是 `iio_info -S usb` 输出 `usb:...` context。

备注：上述“无法建立 IIO context”后来已变化；最新状态是 USB context 正常，IP context 仍失败。

### 阶段 C：拆分真实 TX/RX GRC

**用户：**

> 现在利用plutosdr的模块，如plutosdr source等来进行真实信号的收发，将发信端和收信端的文件分开成两个.grc文件，中间的信号模拟可以先省略，保持其他原功能完整，自行测试并无误后进行修改。在输入源那里用一个默认的信号来作为占位符，保留开赛后需要传递的信号的接口。

**助手关键进度输出：**

> 我会继续按项目中的 SDR/GNU Radio skill 执行：先复核现有单文件流图、Pluto 块参数和测试脚本，再拆成独立的发射端与接收端 `.grc`。发射端会保留一个可替换的“竞赛信号输入接口”，默认接入安全的占位信号；测试阶段只做编译和无硬件发射的结构验证，不会擅自上射频发射。

> 现有工程的协议、FEC、同步、CRC、去重和重组逻辑都在自定义基带块中，原来的硬件接口却是嵌入式 `pyadi-iio`，并非用户要求的 GRC 原生 PlutoSDR Source/Sink。此次拆分会保留这些基带功能，只把射频边界替换为本机 RadioConda 中实际安装的 `gr-iio` Pluto 块。

> 拆分方案已确定：TX 图采用“默认复数正弦占位源 / 竞赛文件协议源”二选一，随后经过有限样本 `Head`、规则授权阀，再进入原生 `PlutoSDR Sink`；RX 图由原生 `PlutoSDR Source` 经过有限采集 `Head`，同时送入原始 IQ 文件和原有同步/FEC/CRC/重组接收器。

> 两份 `.grc` 已生成，并已通过本机 `grcc 3.10.12.0` 编译；生成代码确认实际构造的是 `iio.fmcomms2_sink_fc32` 和 `iio.fmcomms2_source_fc32`，而不是原来的 pyadi 包装块。

> 专项 GRC 测试已全部通过；全库回归曾暴露既有 `operation/08_prepare.py` 只捕获 `ImportError`，而系统 pyadi 因缺少 DLL 抛出 `TypeError`。该准备脚本已改为把不可用的可选硬件后端报告为 INFO，不使离线准备流程崩溃。

> 最终验证已完成：新 TX 默认实例化会在构造 Pluto Sink 之前命中“RF TX gate closed”；两份 GRC 均能由 GNU Radio 3.10.12 `grcc` 生成；新拆分协议逐字节回归通过，全库 145/145 通过。

**助手最终回复：**

> 已完成拆分，工程文件保存在原有独立项目文件夹中：
>
> - `sdr_contest_tx_pluto.grc`
> - `sdr_contest_rx_pluto.grc`
> - `README.md`
>
> 主要实现：TX 使用原生 `PlutoSDR Sink`，默认输入为 100 kHz 复数正弦占位信号；将 `input_mode` 改为 `'contest_file'`、设置 `input_path`，即可切换到比赛文件接口。RX 使用原生 `PlutoSDR Source`，保留同步、解调、FEC、CRC、去重、重组、IQ 保存和指标输出。两份硬件图移除中间信道模拟，旧组合图保留作回归。TX 非循环、有限样本，并在构造 Pluto Sink 前进行赛规和三重授权检查。
>
> 验证：GNU Radio 3.10.12 下两份 GRC 均通过 grcc；生成模块导入正常；协议逐字节恢复通过；默认 TX 安全门通过；全部自动测试 145 passed。当时实际 RF 未测，因为 libiio 尚未发现设备；此后 USB context 已恢复。

### 阶段 D：询问 RX 输出

**用户：**

> 目前接收端的输出是什么？如何查看？

**助手最终回复摘要：**

> RX 默认产生 `decoded_payload.bin`、`run_metrics.json`、`rx_capture.c64`，不完整时保存 `decoded_payload.bin.parts/block_*.bin`。最终文件只有在全部块齐全且 CRC 通过后生成。可用 `Get-FileHash`、`Format-Hex` 查看二进制，用 `ConvertFrom-Json` 查看指标，用 NumPy/Matplotlib 或 GNU Radio File Source + QT GUI sinks 查看 IQ。接收器通常在有限采集结束或 Stop 后完成写入。

### 阶段 E：RX `Unable to create context`

**用户提供的日志：**

```text
Generating: sdr_contest_rx_pluto.py
Executing: E:\radioconda\python.exe -u ...\sdr_contest_rx_pluto.py
ERROR: Unable to find host: 找不到指定的类。
RuntimeError: Unable to create context
```

失败行：

```python
iio.fmcomms2_source_fc32(device_uri if device_uri else iio.get_pluto_uri(), ...)
```

**用户：**

> 出现报错，目前的情况怎么样了

**助手诊断：**

> 错误发生在 RX 图初始化 PlutoSDR Source 时，尚未开始采样，也没有生成新的接收输出。GNU Radio 和 gr-iio 块已成功加载，但 `device_uri='ip:192.168.2.1'` 无法创建 libiio context。

重新检测后得到最新变化：

```text
USB scan: success, URI usb:1.3.5
IP scan: failed
ip:192.168.2.1: timeout 10060
usb:: context created successfully
```

**助手最终回复：**

> 硬件已经可以通过 USB 正常访问，报错原因只是 RX 工程仍使用错误的网络 URI `ip:192.168.2.1`。把 GRC 的 `device_uri` 改为 `'usb:1.3.5'`；如果只接一台 Pluto，也可使用 `'usb:'`。重新 Generate 和 Run。本次失败发生在 Source 构造阶段，因此不会更新 IQ、metrics 或 decoded 文件。拔插后运行 `iio_info -S usb` 获取新 URI。

### 阶段 F：TX `RF TX gate closed`

**用户提供的日志：**

```text
Generating: sdr_contest_tx_pluto.py
Executing: E:\radioconda\python.exe -u ...\sdr_contest_tx_pluto.py
RuntimeError: RF TX gate closed: rf_enable, rules_confirmed and physical_path_confirmed must all be true
```

**用户：**

> 这个又是怎么回事？如何解决？把具体要做的行为告诉我

**助手诊断：**

> 这是预期的安全拦截，不是 GNU Radio 或 Pluto 块故障。TX 默认把三个发射许可开关设为 False；即使打开，`contest_rules.yaml` 中的频率、带宽和时长也必须匹配。不会替用户猜测合法频率或擅自开启发射。

**助手最终给出的操作顺序：**

1. 若只测试软件，不修改安全开关，使用 `sdr_contest_complete.grc` 的 `role='sim'`，或只 Generate 不 Run。
2. 真实发射前关闭其他占用 SDR 的程序。
3. 确认天线/滤波器/假负载或经过计算的有线衰减，禁止 TX 直连 RX。
4. 按正式赛规填写 `contest_rules.yaml`。
5. 把 TX `device_uri` 改成 `'usb:1.3.5'`。
6. 设置真实、已获授权的中心频率、带宽、有限时长，首次保持 `tx_attenuation_db=89.75`。
7. 输入选择：`placeholder` 为占位正弦；比赛文件用 `contest_file` 并设置完整 `input_path`。
8. 只有全部确认后才将 `rf_enable`、`rules_confirmed`、`physical_path_confirmed` 改成 True；同时 YAML 的 `rules.confirmed` 也必须 true。
9. 重新 Generate → Run；`cyclic=False` 且样本数有限。

### 阶段 G：向主办方收集参数

**用户：**

> 整理一个所需的参数表，用于向主办方提问，获取信息。

该输入在上下文中出现了两次，意图相同。

**助手最终回复要点：**

向主办方收集以下类别：

1. 射频：频段上下限、中心频率、最大占用带宽、最大发射功率、最大 TX 增益/最小衰减、单轮发射时长、采样率、换频、多频点、杂散和保护带。
2. 时间：总时长、统一开始/停止方式、提前启动、分阶段、断线重启。
3. 文件/评分：文件大小、格式、输入方式、输出格式、正确字节/完整文件/正确帧计分、连续前缀或任意位置、重复和缺失处理、提交时间。
4. 协议：自定义帧、FEC、交织、CRC、调制、扩频、跳频、OFDM、自适应、训练序列、循环发送、ARQ/ACK、全/半双工、主动干扰、机器学习。
5. 硬件：NanoSDR/Pluto 型号、固件限制、FPGA/校准修改、独立 TX/RX SDR、端口、天线、滤波器、衰减器、空口/屏蔽/有线、外部时钟。
6. 电脑接口：Wi-Fi、蓝牙、以太网、串口、U盘、安装模块、赛中改代码、软件版本、离线启动要求。

最少必须确认：准确频段、中心频率、最大带宽、最大发射功率、单轮时长、评分规则。

建议主办方用以下 YAML 回复：

```yaml
rules:
  confirmed: true
  contest_duration_s:
  scoring_mode:
  feedback_allowed:
  half_duplex_allowed:
  dynamic_frequency_allowed:
  retransmission_allowed:
  cyclic_transmission_allowed:

rf:
  allowed_bands_hz:
    - [频段下限, 频段上限]
  allowed_center_frequencies_hz:
    - 中心频率
  max_occupied_bandwidth_hz:
  max_sample_rate_sps:
  max_tx_power_dbm:
  max_tx_gain_db:
  minimum_tx_attenuation_db:
  max_duty_cycle_percent:

payload:
  minimum_bytes:
  typical_bytes:
  maximum_bytes:
  input_format:
  output_format:
  scoring_alignment:
  partial_file_accepted:
  duplicate_data_counted:

hardware:
  device_model:
  hardware_revision:
  required_firmware_version:
  tx_port:
  rx_port:
  required_filter:
  required_antenna:
  connection_method:
```

### 阶段 H：本交接文件

**用户：**

> 把当前的整个对话，包括我的输入和你的输出，以及所用到的api、skill、需要考虑的参数、思考方向等完整地输出到一个md文件，以供后续的agent进行操作不要因此而改变其他的文件。

**助手行为：**

- 只读核对当前文件、参数和测试收集数量；
- 只新增本文件 `AGENT_HANDOFF_FULL_CONVERSATION.md`；
- 未在本轮修改任何其他文件。

---

## 5. 需要向主办方确认的完整参数表

### 5.1 RF 和功率

| 优先级 | 参数/问题 | 单位或答案 |
|---|---|---|
| 必须 | 允许频段下限 | Hz/MHz |
| 必须 | 允许频段上限 | Hz/MHz |
| 必须 | 是否指定中心频率；具体值 | Hz/MHz |
| 必须 | 最大占用带宽 | Hz/MHz |
| 必须 | 最大发射功率/EIRP | dBm |
| 必须 | Pluto 最大 TX 增益或最小衰减 | dB |
| 必须 | 单轮总时长、单次连续发射时长 | 秒 |
| 建议 | 允许采样率范围 | sample/s |
| 建议 | 是否允许换频、多频点、扩频、跳频 | 是/否及范围 |
| 建议 | 杂散、带外、保护带和频谱模板 | dBc/dBm/Hz |
| 建议 | 最大占空比 | % |

### 5.2 时间、启动与恢复

| 参数/问题 | 答案 |
|---|---|
| 比赛统一开始/停止信号如何给出 |  |
| TX/RX 能否提前启动 |  |
| 超时发射处罚 |  |
| 是否允许掉线后重启流图/设备 |  |
| 轮次之间能否修改参数、代码和模型 |  |

### 5.3 文件和评分

| 参数/问题 | 答案 |
|---|---|
| 文件最小/典型/最大字节数 |  |
| 任意二进制还是指定格式 |  |
| 输入文件交付方式和路径约定 |  |
| 接收输出文件名/格式 |  |
| 按完整文件、正确字节、连续前缀还是正确帧计分 |  |
| 输出长度错误、缺块、重复帧如何计分 |  |
| 是否允许部分文件提交 |  |
| 是否需要日志、IQ、哈希、帧清单 |  |
| 比赛结束后的提交时限 |  |

### 5.4 协议和算法许可

| 参数/问题 | 答案 |
|---|---|
| 自定义帧头、前导和同步序列 |  |
| FEC、交织、CRC、白化 |  |
| 允许的调制方式 |  |
| OFDM、DSSS、跳频、自适应调制编码 |  |
| 重复发送、循环发送、ARQ/ACK |  |
| 单向、半双工、全双工和反馈规则 |  |
| 主动干扰/压制/欺骗波形是否允许 |  |
| 机器学习模型是否允许 |  |

### 5.5 硬件、接口与环境

| 参数/问题 | 答案 |
|---|---|
| NanoSDR/Pluto 精确型号与硬件版本 |  |
| 固件版本，是否允许修改固件/FPGA/校准 |  |
| TX/RX 是否各一台独立 SDR |  |
| 指定 TX/RX 端口 |  |
| 强制天线、滤波器、衰减器 |  |
| 空口、屏蔽箱还是有线衰减测试 |  |
| 外部 LNA/PA/时钟/GPSDO 是否允许 |  |
| SDR 必须走 USB 还是允许网络 IIO |  |
| Wi-Fi、蓝牙、以太网、串口、U盘限制 |  |
| 操作系统、GNU Radio、RadioConda 版本限制 |  |

---

## 6. 后续 Agent 的推荐操作顺序

### 6.1 安全的下一步：RX-only 实机冒烟测试

1. 关闭占用 Pluto 的其他程序。
2. 执行：

   ```powershell
   E:\radioconda\Library\bin\iio_info.exe -S usb
   ```

3. 记录当前 URI 和序列号；不要假设仍是 `usb:1.3.5`。
4. 将 RX GRC 的 `device_uri` 改为精确 URI；为了持久化，同时修改 `build_split_grc.py` 中 RX 默认 URI。
5. RX-only 不需要解除 TX 安全门。先使用短时长、有限样本、合理手动增益或 slow_attack。
6. Generate → Run，等待自动停止。
7. 检查 `rx_capture.c64` 和 `run_metrics.json` 的更新时间、样本数、峰值、均值和频谱。
8. 若没有合法通信信号，`decoded_payload.bin` 不生成是正常的；先证明 IQ 非全零、无 NaN/Inf、无严重饱和。

### 6.2 TX 之前必须完成

1. 从主办方取得本文件第 5 节参数。
2. 填写 `contest_rules.yaml`，不要保留关键 `null`。
3. 确认天线/滤波器/假负载，或计算有线衰减和 RX 最大安全输入。
4. 更新 TX `device_uri` 为实际 USB URI。
5. 使用已授权中心频率和带宽；保持有限时长和 `cyclic=False`。
6. 第一次保持 `tx_attenuation_db=89.75`（最低输出），逐步测试。
7. 只有在上述条件完成后，才设置三个 GRC 布尔门和 YAML `rules.confirmed`。
8. 先启动 RX，再启动 TX；两个程序不要争用同一 USB context，比赛预期使用两台 SDR。
9. 记录输入文件 SHA-256、TX manifest、RX metrics、输出 SHA-256、缺块和吞吐。

### 6.3 修改工程后的验证

```powershell
python gnu_radio_contest_grc\build_split_grc.py

$env:PATH = 'E:\radioconda;E:\radioconda\Library\mingw-w64\bin;E:\radioconda\Library\usr\bin;E:\radioconda\Library\bin;E:\radioconda\Scripts;' + $env:PATH
$env:CONDA_PREFIX = 'E:\radioconda'

E:\radioconda\Library\bin\grcc.exe -o gnu_radio_contest_grc `
  gnu_radio_contest_grc\sdr_contest_tx_pluto.grc `
  gnu_radio_contest_grc\sdr_contest_rx_pluto.grc

python -m pytest -q
```

注意：如果用户已直接在 GRC GUI 中保存了 URI/频率参数，先把这些变化同步进 `build_split_grc.py`，否则生成器会恢复默认值。

---

## 7. 故障诊断索引

### `Unable to create context`

- 先看 URI；当前 IP URI 不可用，USB URI 可用。
- `iio_info -S usb` 是否能发现设备。
- `iio_info -u usb:` 是否能列出 `ad9361-phy` 和 buffer devices。
- 确认没有其他程序占用 context。
- 拔插后 USB 拓扑 URI 可能变化。

### `RF TX gate closed`

- 这是设计行为，不是块故障。
- 检查三个 GRC 布尔门。
- 检查 YAML `rules.confirmed`。
- 检查中心频率、带宽和时长是否落在 YAML 允许范围。
- 没有正式规则或物理路径确认时不要解除。

### 系统 Python `import adi` 报 `NoneType is not iterable`

- 原因：找到 Python 包但找不到原生 libiio 动态库。
- 使用 RadioConda Python，而不是普通系统 Python。
- 不要混用系统 pip、其他 Conda 和 RadioConda 的二进制库。

### RX 没有 `decoded_payload.bin`

- Source 若初始化失败，本轮没有采样。
- 成功采样但没有完整合法帧时，只会有 IQ、metrics，可能有 `.parts`。
- 最终重组通常在流图停止时发生。
- 查看 `frames_detected`、CRC failures、accepted frames、missing blocks。

### TX/RX 参数不匹配

两端必须一致：

```text
center_frequency_hz
samp_rate
rf_bandwidth_hz（至少能覆盖信号）
modulation
fec_mode
samples_per_symbol
rrc_rolloff
rrc_span
preamble_symbols
guard_symbols
seed
```

---

## 8. 本轮文件变更声明

用户要求“不要因此而改变其他文件”。本轮只新增：

```text
C:\Users\16839\Desktop\无线电gpt\AGENT_HANDOFF_FULL_CONVERSATION.md
```

本轮没有修改、删除或重生成其他文件。
