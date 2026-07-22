# SDR 竞赛软件与 API 目录

本目录面向“PlutoSDR/NanoSDR 兼容设备、随机文件传输、同场同频干扰、赛时离线”的通信比赛。它覆盖成熟且实际可用的主要工具族，不声称穷尽所有业余无线电程序。资料核对日期：2026-07-21。

## 目录

1. [最小推荐栈](#最小推荐栈)
2. [环境与主框架](#环境与主框架)
3. [PlutoSDR 与硬件 API](#plutosdr-与硬件-api)
4. [DSP、调制与同步](#dsp调制与同步)
5. [信道编码与数据完整性](#信道编码与数据完整性)
6. [IQ 数据与复现实验](#iq-数据与复现实验)
7. [频谱、波形和协议诊断](#频谱波形和协议诊断)
8. [进程控制与 Agent 接口](#进程控制与-agent-接口)
9. [RadioConda 已包含的相关包](#radioconda-已包含的相关包)
10. [选择规则](#选择规则)
11. [官方来源](#官方来源)

## 最小推荐栈

Windows 双笔记本、两台 Pluto 兼容 NanoSDR 的首选基线：

| 层 | 首选 | Agent 接口 | 作用 |
|---|---|---|---|
| 离线环境 | RadioConda | `conda`、`mamba`、环境锁文件 | 固定 GNU Radio、驱动和科学计算依赖 |
| 完整链路 | GNU Radio 3.10 + gr-iio | Python/C++、GRC YAML、`grcc` | 收发流图、同步、调制、FEC、监测 |
| 快速硬件脚本 | pyadi-iio | Python `adi.Pluto` | 设备配置、有限 IQ 收发、自动化测试 |
| 驱动诊断 | libiio | C/C++/C#/Python、`iio_info`/`iio_attr` | URI 发现、属性和缓冲区诊断 |
| 算法验证 | NumPy + SciPy | Python | FFT、相关、滤波、仿真、指标 |
| 纠错 | GNU Radio FEC | `gnuradio.fec`、GRC blocks | 卷积码、LDPC 等随本地版本提供的编码器 |
| 记录格式 | SigMF | JSON 元数据 + Python | 轻量、可交换的 IQ 捕获 |
| 人工诊断 | inspectrum + pyFDA | GUI/文件 | 码元率、频偏、滤波器和波形检查 |
| 回归测试 | pytest + bundled scorers | Python/CLI | 固定种子、参数扫描和正确字节评分 |

不要同时在第一版引入 GNU Radio、SoapySDR、SDRangel 和自定义 libiio 流式代码。先选一个主数据路径，其余只作诊断或替代。

## 环境与主框架

### RadioConda

- 定位：面向软件无线电的 Conda 发行环境，不是射频运行时 API。
- 自动化入口：`conda`、`mamba`、`conda run`、环境/包列表和锁文件。
- 平台：Windows x86-64、Linux 多架构、macOS Intel/ARM。
- 竞赛价值：一次安装 GNU Radio、Digital RF、gqrx、inspectrum、pyadi-iio、libiio、SoapySDR 及多种设备模块；适合提前冻结后离线运行。
- 注意：赛前保存确切安装器、锁文件和自有代码；不要在赛场 `mamba upgrade --all`。

官方：[installer](https://github.com/radioconda/radioconda-installer)、[当前环境清单](https://github.com/radioconda/radioconda-installer/blob/main/radioconda.yaml)

### GNU Radio / GNU Radio Companion

- 定位：通用流式 DSP 和软件无线电框架，是本赛制的首选完整链路框架。
- API：Python 与 C++ blocks；`gr.top_block`/`start()`/`stop()`/`wait()`；消息端口 PMT/PDU；GRC `.grc` YAML；`grcc` 生成代码。
- 核心模块：`blocks`、`analog`、`digital`、`filter`、`fft`、`fec`、`channels`、`zeromq`、`iio`。
- 适合：持续收发、包流、软判决、同步、频偏校正、均衡、实时监控和自定义块。
- Agent 策略：优先维护 Python 或可生成的 `.grc`，不要依赖鼠标操作 GUI。

官方：[Python 教程](https://wiki.gnuradio.org/index.php/Guided_Tutorial_GNU_Radio_in_Python)、[top_block API](https://www.gnuradio.org/doc/doxygen/classgr_1_1top__block.html)、[包通信](https://wiki.gnuradio.org/index.php/Packet_Communications)、[YAML GRC](https://wiki.gnuradio.org/index.php/YAML_GRC)

### MATLAB / Simulink（付费替代）

- 定位：通信算法、System object 和模型化设计环境。
- API：`sdrrx('Pluto')`、`sdrtx('Pluto')`、`findPlutoRadio`、`capture`、`comm.SDRRxPluto`、`comm.SDRTxPluto`，以及 Simulink Pluto Receiver/Transmitter blocks。
- 优点：课程材料、调制/FEC/同步函数丰富，硬件支持包成熟。
- 缺点：许可证和离线授权必须赛前确认；Agent 生成/调试 Simulink 模型通常不如 Python/GNU Radio 直接。

官方：[Pluto 支持包](https://www.mathworks.com/matlabcentral/fileexchange/61624-communications-toolbox-support-package-for-analog-devices-adalm-pluto-radio)、[`sdrrx`](https://www.mathworks.com/help/comm/plutoradio/ref/sdrrx.html)

### SDRangel（服务器/REST 替代）

- 定位：跨平台 RX/TX、频谱分析和大量现成 modem/plugin 的应用，也有无头服务器版本。
- API：Swagger 定义的 HTTP REST WebAPI；设备集、设备、信道和运行状态端点；Python 可用 `requests` 调用。
- 适合：需要现成服务器、远程参数控制、PER 测试或插件时。
- 不适合：需要深度自定义帧同步和编码管线却又要绕过其插件模型时。

官方：[项目主页](https://www.sdrangel.org/)、[Swagger WebAPI](https://github.com/f4exb/sdrangel/blob/master/swagger/sdrangel/README.md)、[Python PTT 示例](https://github.com/f4exb/sdrangel/blob/master/swagger/sdrangel/examples/ptt.py)

## PlutoSDR 与硬件 API

### pyadi-iio

- 定位：ADI 为 IIO 硬件提供的高层 Python 抽象；Pluto/NanoSDR 脚本首选。
- 安装名：`pyadi-iio`；导入名：`adi`；依赖 `libiio`/`pylibiio` 和 NumPy。
- 关键 API：`adi.Pluto(uri=...)`、`sample_rate`、`rx_lo`、`tx_lo`、`rx_rf_bandwidth`、`tx_rf_bandwidth`、`gain_control_mode_chan0`、`rx_hardwaregain_chan0`、`tx_hardwaregain_chan0`、`rx_buffer_size`、`rx()`、`tx()`、`tx_cyclic_buffer`、`tx_destroy_buffer()`。
- 适合：捕获固定长度 IQ、参数扫描、校准、有限突发和快速回归测试。
- 风险：cyclic buffer 会持续发送，必须显式销毁；`tx_hardwaregain_chan0` 在 AD936x API 中表示 TX 衰减/硬件增益设置，不能按其他设备的“正增益”语义套用。

官方：[文档](https://analogdevicesinc.github.io/pyadi-iio/)、[Pluto/ad936x API](https://analogdevicesinc.github.io/pyadi-iio/devices/adi.ad936x.html)、[buffer 生命周期](https://analogdevicesinc.github.io/pyadi-iio/buffers/index.html)、[连接 URI](https://analogdevicesinc.github.io/pyadi-iio/guides/connectivity.html)

### libiio / pylibiio

- 定位：ADI IIO 的跨平台底层访问库。
- API：C 主 API及 C++、C#、Python bindings；context/device/channel/attribute/buffer/stream 对象。
- CLI：`iio_info`、`iio_attr`、`iio_readdev`、`iio_writedev`。
- 适合：发现 `usb:`/`ip:` context、核对设备属性、诊断驱动和实现最低层流式 I/O。
- Agent 策略：先用 `iio_info -s` 和只读属性；除非高层 API 缺功能，否则不要直接写 debug attributes/registers。

官方：[libiio 文档](https://analogdevicesinc.github.io/libiio/)、[源代码](https://github.com/analogdevicesinc/libiio)

### gr-iio / GNU Radio Pluto Source & Sink

- 定位：GNU Radio 与 IIO/Pluto 的直接集成。
- API：GRC 的 PlutoSDR/IIO Source、Sink；生成后的 Python block constructors/setters。
- 适合：持续 modem 链路和图形化调试。
- 版本提示：ADI 文档说明 GNU Radio 3.10 起 gr-iio 已进入基础安装；仍需确认 RadioConda 的本地 block 名称和参数。

官方：[GNU Radio and IIO Devices](https://wiki.analog.com/resources/tools-software/linux-software/gnuradio)、[PlutoSDR Source](https://wiki.gnuradio.org/index.php/PlutoSDR_Source)

### SoapySDR + SoapyPlutoSDR

- 定位：跨厂商 SDR 抽象层。
- API：C++ 核心，C/Python bindings；`Device.enumerate/make`、频率/采样率/带宽/增益设置、`setupStream`、`activateStream`、`readStream`、`writeStream`。
- CLI：`SoapySDRUtil --find`、`--probe`、`--info`。
- 适合：同一套程序切换 Pluto、HackRF、Lime、USRP 等设备。
- 代价：设备专有能力和异常语义需要通过 driver capability 查询，不要假设所有实现都支持定时突发或同样的增益范围。

官方：[Device API](https://pothosware.github.io/SoapySDR/doxygen/latest/classSoapySDR_1_1Device.html)、[源代码](https://github.com/pothosware/SoapySDR)

### IIO Oscilloscope

- 定位：ADI 官方的 IIO 设备 GUI，适合查看频谱、时域和硬件属性。
- API：主要是 GUI 和底层 libiio；没有比 pyadi-iio 更适合 Agent 的稳定高层自动化面。
- 用途：安装/驱动验证、快速排除硬件问题，不作竞赛主收发程序。

官方：[iio-oscilloscope](https://github.com/analogdevicesinc/iio-oscilloscope)

### 其他硬件 API（换设备时）

| 设备族 | 官方 API/CLI | 说明 |
|---|---|---|
| USRP | UHD C++/Python、`uhd_find_devices` | 高质量定时/流式 API；RadioConda 包含 UHD |
| HackRF | libhackrf C、`hackrf_info`/`hackrf_transfer` | 半双工；不替代本赛制 Pluto API |
| LimeSDR | Lime Suite C/C++、SoapyLMS7 | 可通过 Soapy 或原生 API |
| bladeRF | libbladeRF C、CLI | 原生流式 API和工具 |
| RTL-SDR | librtlsdr C、`rtl_sdr`/`rtl_test` | 仅接收，不能承担比赛 TX |

RadioConda 的官方设备表列出了这些库及其驱动安装注意事项。

## DSP、调制与同步

### NumPy / SciPy

- API：Python ndarray、`numpy.fft`/`scipy.fft`、`scipy.signal` 的 FIR/IIR、相关、重采样、Welch、STFT、峰值检测等。
- 适合：离线算法、向量化 modem 原型、频偏/同步验证、参数扫描和评分。
- 不适合：仅靠普通 Python 循环承担持续高采样率实时流；实时路径应使用 GNU Radio/C++/VOLK。

官方：[NumPy](https://numpy.org/doc/stable/)、[`scipy.signal`](https://docs.scipy.org/doc/scipy/reference/signal.html)

### liquid-dsp

- 定位：轻量 C DSP/通信库。
- API：C objects/functions；modem、NCO、AGC、同步、均衡、FEC、packetizer、flexframe、OFDM flexframe、channel emulator。
- 适合：需要比 GNU Radio 更紧凑的自定义 C/C++ modem 或独立性能实验时。
- 注意：与 Pluto 连接仍需 libiio/SoapySDR 等硬件层。

官方：[模块目录](https://liquidsdr.org/doc/)、[OFDM framing 教程](https://liquidsdr.org/doc/tutorial-ofdmflexframe/)

### VOLK

- 定位：GNU Radio 的 SIMD 优化内核集合。
- API：C/C++ kernels、profile/config 工具。
- 适合：确认 CPU 热点后优化相关、乘法、类型转换等；GNU Radio 已广泛使用。
- 不要在算法尚未正确时手写 SIMD。

官方：[gnuradio/volk](https://github.com/gnuradio/volk)

### pyFDA

- 定位：滤波器设计 GUI，RadioConda 已包含。
- API：Python 应用/模块和系数导出；自动化稳定性不如 SciPy API。
- 适合：人工比较通带、阻带、阶数和量化；将最终系数固化到代码并回归测试。

官方：[pyfda](https://github.com/chipmuenk/pyfda)

### Sionna PHY（可选）

- 定位：GPU 加速、可微的链路级通信仿真。
- API：Python；调制、信道、编码和端到端学习组件。
- 适合：赛前探索 LDPC、软信息、学习型接收机；不应成为没有 GPU/依赖锁定的赛场必需项。

官方：[Sionna 文档](https://nvlabs.github.io/sionna/index.html)

## 信道编码与数据完整性

### GNU Radio FEC

- API：Python `from gnuradio import fec`、GRC FEC encoder/decoder/deployment blocks。
- 能力：具体卷积码、LDPC、重复码等由安装版本决定；运行 `help(fec)` 并检查本地 blocks。
- 适合：直接接入流图并传递软信息。

官方：[Using the FEC API](https://www.gnuradio.org/doc/doxygen/page_fec.html)

### liquid-dsp FEC / packetizer

- API：C `fec`、`packetizer`、CRC、interleaver、`qpacketmodem` 和 framing objects。
- 适合：一体化 C modem 或快速评估多种码率/调制组合。

官方：[liquid-dsp 文档](https://liquidsdr.org/doc/)

### AFF3CT

- 定位：高吞吐 C++ FEC 仿真器和库。
- API：命令行模拟器、C++ library；社区有 Python wrapper，但不要把非核心 wrapper 作为基线。
- 能力：Turbo、LDPC、Polar 等。
- 适合：赛前曲线评估、复杂 FEC 性能比较和 C++ 集成。

官方：[AFF3CT](https://aff3ct.github.io/)、[源代码](https://github.com/aff3ct/aff3ct)

### libcorrect / reedsolo（轻量备选）

- libcorrect：C API，卷积码/Viterbi 与 Reed-Solomon；适合小型原生模块。
- reedsolo：Python/Cython 的 Reed-Solomon 包；易用但吞吐和流式集成需实测。
- 不要把多个 FEC 库叠加在同一基线中；先以软判决、交织和帧丢失模型进行比较。

官方：[libcorrect](https://github.com/quiet/libcorrect)、[reedsolo](https://github.com/tomerfiliba-org/reedsolomon)

## IQ 数据与复现实验

### SigMF / sigmf-python

- 格式：二进制 dataset 加 JSON metadata；记录 datatype、sample rate、capture frequency、时间和注释。
- API：SigMF schema/spec；Python `sigmf` 包。
- 适合：每次实验的便携 IQ 捕获、频率/采样率不丢失、跨工具交换。

官方：[SigMF 规范](https://sigmf.org/)、[sigmf-python](https://github.com/sigmf/sigmf-python)

### Digital RF

- 格式：基于 HDF5、支持快速随机访问和长时归档。
- API：Python、C、MATLAB、GNU Radio blocks (`gr_digital_rf`)。
- 适合：长时间、多段、带时间索引的捕获；短比赛回归可优先 SigMF。

官方：[Digital RF](https://github.com/MITHaystack/digital_rf)

### Raw IQ / HDF5

- Raw IQ：GNU Radio File Sink、NumPy `tofile/fromfile`，简单但必须另存 datatype/endian/sample-rate/frequency。
- HDF5：`h5py` Python API，便于数组、属性、日志统一存储，但不是通用 RF 交换标准。
- 无论何种格式，都记录样本格式（如 complex64/CS16）、满量程约定和是否发生缩放。

## 频谱、波形和协议诊断

| 工具 | 主要用途 | Agent/API 评价 |
|---|---|---|
| inspectrum | 大型 IQ 文件的频谱、相位、码元周期和选区导出 | GUI/文件为主；适合人工诊断，不是主自动化 API |
| URH | 未知数字协议的调制检测、解码、字段分析和仿真 | Python 项目、有 CLI/原生设备支持；用于诊断，不要依赖内部未承诺 API |
| SigDigger | 基于 Soapy/Suscan/Sigutils 的实时信号分析 | GUI；底层 C 库更适合程序化扩展 |
| SDRangel | 实时频谱、modem、PER 与设备控制 | REST API 最适合 Agent |
| gqrx | 通用接收机和频谱 GUI | 主要用于人工 RX 验证；无自定义竞赛 modem 主 API |
| Wireshark/TShark | 已恢复 packet/pcap 的字段检查和自定义 dissector | `tshark` CLI、Lua/C dissector；不直接处理原始 IQ |
| GNU Radio QT GUI sinks | 实时频谱/瀑布/星座/时域 | Python/GRC 可生成，但无头赛场程序应可关闭 GUI |
| pyFDA | FIR/IIR 设计与量化检查 | GUI/系数导出；最终实现交给 SciPy/GNU Radio |

官方：[inspectrum](https://github.com/miek/inspectrum)、[URH](https://github.com/jopohl/urh)、[SigDigger](https://github.com/BatchDrake/SigDigger)、[gqrx](https://github.com/gqrx-sdr/gqrx)、[TShark](https://www.wireshark.org/docs/man-pages/tshark.html)

### SDR++ / CubicSDR / Pothos（次要替代）

- SDR++、CubicSDR：优质通用接收 GUI，但自定义 Agent 控制面和文件 modem 工作流不如 GNU Radio/SDRangel。
- Pothos：数据流开发环境，与 SoapySDR 生态契合；如果团队已有经验可用，否则不应在临赛替换 GNU Radio。
- 将它们作为设备/频谱 sanity check，而非首版比赛架构。

官方：[SDR++](https://github.com/AlexandreRouma/SDRPlusPlus)、[CubicSDR](https://github.com/cjcliffe/CubicSDR)、[Pothos](https://github.com/pothosware/PothosCore)

## 进程控制与 Agent 接口

### 最可靠的调用优先级

1. 直接导入 Python API：GNU Radio、pyadi-iio、NumPy/SciPy、SigMF。
2. 执行有确定退出码和 JSON/文本输出的 CLI：probe/scorer、`iio_info`、`SoapySDRUtil`、`grcc`、`tshark`。
3. 使用本机 REST：SDRangel WebAPI，或为自有控制器封装 FastAPI。
4. 使用 GNU Radio 消息端口/ZeroMQ 传递本机控制和统计。
5. 仅在遗留 flowgraph 中使用 XML-RPC；ControlPort 更偏运行期检测和调试。
6. 最后才考虑 GUI 自动化。

### GNU Radio 的运行期接口

- Python setter/getter：最直接，适合 Agent 启动的同一进程。
- PMT/PDU message ports：块间控制和 packet 数据。
- ZeroMQ blocks：跨进程 stream/message；比赛规则若禁止其他通信接口，应只绑定 loopback 或本机 IPC，并确认合规。
- XML-RPC blocks：控制无头 flowgraph 的传统方案。
- ControlPort：标准化远程过程调用和性能/状态检查；部署前确认本地构建已启用。

官方：[Message Passing](https://wiki.gnuradio.org/index.php/Message_Passing)、[XML-RPC](https://wiki.gnuradio.org/index.php/Understanding_XMLRPC_Blocks)、[ControlPort](https://wiki.gnuradio.org/index.php/ControlPort)

### MCP/HTTP 封装建议

当 Agent 不能直接访问本机 shell/USB 时，在比赛电脑本地封装最小接口：

```text
list_devices
read_device_info
start_rx / stop_rx
capture_iq
get_run_metrics
validate_tx_plan
start_finite_tx / stop_tx
```

让服务器端再次校验频段、带宽、等级、持续时间和物理确认。不要暴露任意 shell、任意 IIO attribute 写入或无限 cyclic TX。

## RadioConda 已包含的相关包

当前官方 `radioconda.yaml` 明确包含或约束以下竞赛相关组件：

- `gnuradio 3.10.*`、`digital_rf`、`libiio`、`pyadi-iio`；
- `soapysdr` 与 Pluto/HackRF/Lime/RTL-SDR/UHD/remote 等 modules；
- `numpy`、`scipy`、`matplotlib`、`pandas`、`ipython`、`pyfda`；
- `gqrx`、`inspectrum`；
- GNU Radio OOT：`gnuradio-inspector`、`gnuradio-iqbalance`、`gnuradio-ieee802_11`、`gnuradio-ieee802_15_4`、`gnuradio-lora_sdr`、`gnuradio-paint`、`gnuradio-radar` 等；
- 各类设备库：UHD、HackRF、LimeSuite、bladeRF、rtl-sdr 等。

OOT 使用原则：

- `inspector`/`iqbalance` 可用于识别和前端校正实验；
- 802.11/802.15.4/LoRa 模块可作参考实现或规则允许时的候选，不等于最优文件传输方案；
- `paint` 等频谱生成模块只可用于规则和场地明确授权的干扰测试；
- OOT 的本地 GNU Radio 兼容性必须在冻结环境中验证。

## 选择规则

| 需求 | 首选 | 次选 | 避免 |
|---|---|---|---|
| Pluto 快速收发脚本 | pyadi-iio | libiio | GUI 宏 |
| 完整实时 modem | GNU Radio + gr-iio | liquid-dsp + libiio | Python 逐样本循环 |
| 多品牌 SDR | SoapySDR | 各厂商原生 API | 假设设备能力完全一致 |
| 远程/无头 REST | SDRangel | 自建受限 FastAPI/MCP | 裸 shell endpoint |
| FEC 快速集成 | GNU Radio FEC | liquid-dsp | 同时混用多套 bit/LLR 约定 |
| 高级 LDPC/Polar 研究 | AFF3CT/Sionna | 自定义 | 临赛第一次集成 |
| 短 IQ 回归 | SigMF | raw + sidecar JSON | 无元数据 raw 文件 |
| 长时 IQ 归档 | Digital RF | HDF5 | 全量装入内存 |
| 人工码元诊断 | inspectrum/URH | SigDigger | 从截图猜参数 |
| 解码后的包分析 | TShark/Wireshark | Python parser | 把 pcap 当 IQ |

## 官方来源

- [RadioConda installer 与设备支持](https://github.com/radioconda/radioconda-installer)
- [RadioConda 完整环境规范](https://github.com/radioconda/radioconda-installer/blob/main/radioconda.yaml)
- [ADALM-PLUTO 官方产品/API 能力](https://www.analog.com/en/resources/evaluation-hardware-and-software/evaluation-boards-kits/adalm-pluto.html)
- [pyadi-iio](https://analogdevicesinc.github.io/pyadi-iio/)
- [libiio](https://analogdevicesinc.github.io/libiio/)
- [GNU Radio](https://wiki.gnuradio.org/)
- [SoapySDR](https://pothosware.github.io/SoapySDR/doxygen/latest/)
- [liquid-dsp](https://liquidsdr.org/doc/)
- [AFF3CT](https://aff3ct.github.io/)
- [SigMF](https://sigmf.org/)
- [Digital RF](https://github.com/MITHaystack/digital_rf)

