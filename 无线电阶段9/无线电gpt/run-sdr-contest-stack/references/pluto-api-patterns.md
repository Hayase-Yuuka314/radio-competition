# PlutoSDR/NanoSDR API 调用模式

## 目录

1. [接口优先级](#接口优先级)
2. [发现与绑定设备](#发现与绑定设备)
3. [pyadi-iio 接收模式](#pyadi-iio-接收模式)
4. [pyadi-iio 发射模式](#pyadi-iio-发射模式)
5. [GNU Radio/gr-iio 模式](#gnu-radiogr-iio-模式)
6. [libiio 诊断模式](#libiio-诊断模式)
7. [SoapySDR 可移植模式](#soapysdr-可移植模式)
8. [常见故障定位](#常见故障定位)

## 接口优先级

| 任务 | 使用 |
|---|---|
| 固定长度 IQ capture、参数扫描 | pyadi-iio |
| 完整实时 modem/stream graph | GNU Radio + gr-iio |
| context、属性和 driver 诊断 | libiio CLI/Python |
| 需要切换多品牌 SDR | SoapySDR |
| 需要现成 REST server/plugins | SDRangel |

避免让两个框架同时打开同一 SDR。关闭上一个 context/flowgraph 后再切换工具。

## 发现与绑定设备

先运行只读发现：

```bash
iio_info -s
SoapySDRUtil --find
```

常见 URI 形式：

```text
ip:192.168.2.1
ip:pluto.local
usb:
usb:1.24.5
```

不要假设所有 Pluto 兼容板都使用同一地址、固件或 USB backend。两台设备可能同时可见时，用序列号/完整 URI 绑定角色，并把绑定记录进 run manifest。

## pyadi-iio 接收模式

只读 capture 的最小结构：

```python
import adi
import numpy as np

sdr = adi.Pluto(uri=DEVICE_URI)
sdr.sample_rate = SAMPLE_RATE
sdr.rx_lo = CENTER_FREQUENCY
sdr.rx_rf_bandwidth = RF_BANDWIDTH
sdr.gain_control_mode_chan0 = GAIN_MODE
if GAIN_MODE == "manual":
    sdr.rx_hardwaregain_chan0 = RX_GAIN_DB
sdr.rx_buffer_size = BUFFER_SAMPLES

iq = np.asarray(sdr.rx())
```

要求：

- 读取属性回读值并记录，因为硬件可能量化请求值；
- 丢弃或单独标记启动后的若干 buffer，由实测决定 warm-up 数；
- 检查 dtype、幅度、DC、clipping、缺样/异常；
- 将中心频率、采样率、带宽、增益模式和 URI 写入 SigMF 或 sidecar JSON；
- 不在高采样率循环中反复创建绘图或大对象。

官方 API 属性见 [adi.ad936x.Pluto](https://analogdevicesinc.github.io/pyadi-iio/devices/adi.ad936x.html)。

## pyadi-iio 发射模式

只在 `validate_radio_plan.py` 通过且物理连接已确认后生成真正参数。保持以下结构：

```python
sdr = None
try:
    sdr = adi.Pluto(uri=plan["device"]["uri"])
    sdr.sample_rate = int(tx["sample_rate_sps"])
    sdr.tx_lo = int(tx["center_frequency_hz"])
    sdr.tx_rf_bandwidth = int(tx["occupied_bandwidth_hz"])
    sdr.tx_hardwaregain_chan0 = float(tx["level"]["value"])
    sdr.tx_cyclic_buffer = bool(tx["cyclic"])
    sdr.tx(iq_for_device)
    # Enforce the validated finite run duration here.
finally:
    if sdr is not None:
        sdr.tx_destroy_buffer()
```

生成实现时补齐：

- 在同一进程内加载并验证 plan/constraints；
- 按 pyadi-iio/固件所需的数据位宽缩放 IQ，记录 peak/RMS/PAPR；
- 限幅前检查峰值，禁止无意 wrap-around；
- 非 cyclic 模式明确 buffer/stream 的完成语义；
- cyclic 模式用 `try/finally`、有限计时器和外部 stop action 三重保护；
- 捕获 `KeyboardInterrupt` 并销毁 TX buffer；
- 退出后读回/确认运行状态，不能只相信程序日志。

pyadi-iio 官方说明 cyclic buffer 会持续发送，更新或停止前必须 `tx_destroy_buffer()`：[Buffers](https://analogdevicesinc.github.io/pyadi-iio/buffers/index.html)。

不要直接把这一结构复制后填入猜测频率。频率、带宽、duration 和 level 必须来自经过确认的 constraints。

## GNU Radio/gr-iio 模式

### 推荐生成策略

1. 在 GRC 中验证 block 名称、参数表达式和端口类型。
2. 保存 `.grc` YAML 作为可视设计源。
3. 使用 GRC/`grcc` 生成 Python，并由 Agent 检查生成代码中的构造器和 setters。
4. 将 payload/framing/modem 写成层级 block 或独立 Python/C++ block。
5. 让无头生产模式可禁用所有 QT GUI sinks。

典型 TX block graph：

```text
File/Vector/PDU Source
 -> Framer/FEC/Modulator
 -> Scale/Limiter
 -> PlutoSDR Sink
```

典型 RX block graph：

```text
PlutoSDR Source
 -> channel filter/resampler
 -> synchronization/demod/FEC
 -> packet handler
 -> File Sink + metrics
```

使用 setters 只改明确允许运行期变化的参数。中心频率或采样率变化可能要求重建/重启部分 graph；用本地版本做实测，不要假设 setter 无缝生效。

对连续 flowgraph：

```python
tb.start()
try:
    run_control_loop()
finally:
    tb.stop()
    tb.wait()
```

将设备异常、buffer overflow/underflow 和 decoder counters 输出到结构化日志。

## libiio 诊断模式

优先只读：

```bash
iio_info -s
iio_info -u ip:192.168.2.1
iio_attr -u ip:192.168.2.1 -d ad9361-phy
```

具体 CLI 参数会随 libiio 0.x/1.x 变化，先运行本机 `--help`。

Python 入口：

```python
import iio
ctx = iio.Context(DEVICE_URI)
for dev in ctx.devices:
    print(dev.name)
```

用 libiio 做：

- context scan；
- device/channel/attribute 枚举；
- 校验 pyadi-iio 读回；
- 在高层 API 缺失时实现 buffer stream。

不要让 Agent 任意写 `debug_attrs` 或寄存器。寄存器操作可能改变校准、状态机或 FPGA 行为，除非用户明确请求且有设备专用依据。

官方：[libiio](https://analogdevicesinc.github.io/libiio/)、[pyadi 的 libiio entry points](https://analogdevicesinc.github.io/pyadi-iio/libiio.html)。

## SoapySDR 可移植模式

发现和 capability probe：

```bash
SoapySDRUtil --find
SoapySDRUtil --probe="driver=plutosdr"
```

Python/C++ 的正确顺序：

1. enumerate/make 指定设备；
2. 查询频率、采样率、带宽、增益、天线和 stream format 范围；
3. 设置 RX/TX 参数；
4. `setupStream`；
5. `activateStream`；
6. `readStream`/`writeStream`；
7. `deactivateStream`、`closeStream`、unmake。

处理返回的样本数、flags、时间戳和错误码。不要假设一次 read/write 填满请求 buffer。

官方：[SoapySDR Device API](https://pothosware.github.io/SoapySDR/doxygen/latest/classSoapySDR_1_1Device.html)。

## 常见故障定位

### 看不到设备

1. 检查供电、数据线和 OS 设备管理器。
2. 运行 `iio_info -s`；若失败，再检查 libiio/USB driver。
3. 尝试精确 `usb:` URI 与 `ip:192.168.2.1`，记录哪一 backend 工作。
4. 在 Windows 核对 ADI 官方 driver，不要随意用 Zadig 替换一个原本正常的 Pluto 复合设备接口。
5. 用 IIO Oscilloscope 或 pyadi RX-only 验证最小访问。

### `import adi`/`import iio` 失败

1. 输出当前 `sys.executable`、`CONDA_PREFIX` 和 `python -m pip --version`。
2. 确认 Agent 使用 RadioConda 自带 Python，而不是系统/PyCharm 的另一个解释器。
3. 检查 `pyadi-iio`、`pylibiio` 和 libiio binary 是否在同一环境可见。

### DLL/共享库错误

1. 从 RadioConda Prompt 启动，保留其 PATH/DLL 搜索路径。
2. 不要把系统 pip、另一个 Conda 和 RadioConda 的库混用。
3. 输出确切 DLL/so 名和架构；确认都是 x86-64 或同一目标架构。

### RX 全零、饱和或严重 DC

1. 读回 LO、bandwidth、sample rate、gain mode。
2. 检查天线/滤波器频段和端口。
3. 比较 manual gain 与 AGC；记录峰值和直流均值。
4. 用已知信号和衰减后的有线路径排除环境因素。
5. 不要先用复杂 decoder 掩盖前端错误。

### TX underflow / RX overflow

1. 降低 sample rate 或减少 GUI/磁盘 I/O。
2. 预分配 buffer，避免 Python 逐样本处理。
3. 分离实时 DSP 与日志/绘图线程。
4. 记录持续时间和首次错误时间。
5. 确认 USB hub、电源管理和线缆不会限速/断连。

### cyclic TX 无法停止

1. 调用 `tx_destroy_buffer()`；
2. 在 `finally` 中再次清理；
3. 停止 flowgraph/device sink；
4. 只在必要时断开设备；
5. 重新接收/频谱检查，确认载波已消失。

