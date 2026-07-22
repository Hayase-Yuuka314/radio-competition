# 电波对决竞赛工作流

## 目录

1. [从图片得到的已知条件](#从图片得到的已知条件)
2. [仍需从完整规程确认的条件](#仍需从完整规程确认的条件)
3. [推荐系统结构](#推荐系统结构)
4. [逐级实现路线](#逐级实现路线)
5. [抗干扰设计清单](#抗干扰设计清单)
6. [双电脑部署](#双电脑部署)
7. [实验矩阵与验收](#实验矩阵与验收)
8. [常见错误](#常见错误)

## 从图片得到的已知条件

将这些信息视为当前任务上下文，而不是完整规则：

- 场景模拟共享频谱和有限资源下的卫星通信。
- 每队使用一台 SDR 发射、另一台 SDR 接收。
- 传输内容是组委会提供的随机数文件。
- 多队同时收发，每队发射信号会成为其他队的有源干扰。
- 排名按正确解调的有效数据量决定。
- 参赛电脑需关闭 SDR 以外的所有通信接口。
- 每队有两台 NanoSDR 软件无线电开发板（兼容 PlutoSDR）。
- 物料包括一只 2.4 GHz 带通滤波器、一只 433 MHz 带通滤波器，以及两副对应频段天线。
- 每队自备两台笔记本和电源。

## 仍需从完整规程确认的条件

在设计最终波形前，逐项取得原文：

- 433 MHz 与 2.4 GHz 的确切允许频率边界，而不只是中心频段称呼；
- 最大占用带宽、采样率、发射电平/EIRP 和杂散限制；
- 单轮时长、启动方式、是否允许赛中换频；
- 两个频段是任选、轮换、同时使用还是由裁判指定；
- 是否允许扩频、跳频、自适应调制、重复发送、ARQ 或反向链路；
- 是否允许任何形式的显式干扰波形，还是仅允许自己的通信信号产生自然干扰；
- 随机文件大小、交付接口、输出文件格式和裁判的字节对齐/重复处理规则；
- 是否按正确唯一字节、连续前缀、完整帧、吞吐率或其他公式计分；
- 训练和比赛时 SDR 固件、驱动及软件版本是否受限制。

对未知项建立 `UNKNOWN`，禁止用常见 ISM 频段边界替代竞赛原文。

## 推荐系统结构

### 发射端

```text
random file
  -> chunker
  -> frame header: magic/version/sequence/length/mode
  -> payload CRC
  -> FEC encoder
  -> block interleaver
  -> whitening/scrambling
  -> robust PHY header
  -> preamble + training
  -> BPSK/QPSK or selected modulation
  -> RRC/pulse shaping
  -> finite TX buffer / streaming sink
```

### 接收端

```text
SDR source
  -> DC blocker / optional IQ correction
  -> channel filter / resampler
  -> energy or correlation detector
  -> coarse CFO correction
  -> timing recovery
  -> fine carrier recovery
  -> equalizer when needed
  -> soft demapper
  -> robust PHY header decode
  -> dewhitening/deinterleaving/FEC
  -> CRC
  -> deduplication/reordering
  -> decoded file + packet log
```

让 header 的编码和调制至少与 payload 一样稳健，通常应更稳健。没有可靠 header，就无法安全解释 payload 的调制、码率和长度。

## 逐级实现路线

### Level 0：纯文件链路

- 用固定随机种子生成 payload。
- 实现分片、序号、长度、CRC、FEC、交织和重组。
- 保证无信道损伤时逐字节一致。
- 建立 scorer 和帧级日志。

### Level 1：复基带仿真

- 先用 BPSK 或 QPSK + RRC 建立单载波基线。
- 注入 AWGN、随机初相位、CFO、SRO 和不同起始偏移。
- 给解码器使用 LLR/soft bits，而不是过早硬判决。
- 输出同步成功率、header 成功率、CRC 成功率、正确字节/秒。

### Level 2：干扰模型

逐个添加并单独标注：

- 单音/多音窄带干扰；
- 部分带宽噪声；
- 宽带噪声；
- 同制式异步 co-channel packets；
- 不同符号率和调制的 co-channel waveform；
- burst interference；
- near-far 场景、ADC clipping 和 AGC pumping。

随后做组合场景。不要只用 AWGN 推断同场表现。

### Level 3：IQ 文件回放

- 固化 IQ datatype、采样率、中心频率、增益、时间和硬件信息。
- 对同一 capture 重复运行 decoder，要求结果确定。
- 用 inspectrum/URH/频谱图解释失败，而不是盲调参数。

### Level 4：有线/屏蔽硬件

- 核算 TX 输出、衰减器、线损和 RX 最大安全输入。
- 通过合路器/衰减器加入第二信号源作为可控干扰。
- 记录 overflow、underflow、实际采样率和持续运行稳定性。
- 对两块 NanoSDR 分别记录 URI/serial，禁止依靠枚举顺序。

### Level 5：授权 OTA

- 装上正确频段的滤波器和天线。
- 从低发射等级开始验证频谱和接收。
- 运行有限时长并保留一键停止。
- 只在规程允许范围内测试频率选择、冗余或自适应策略。

## 抗干扰设计清单

### 优先实现

- 高处理增益的相关前导和重复训练符号；
- 分层同步：能量/相关检测、粗频偏、细频偏、定时；
- 软判决 FEC；
- 跨干扰 burst 的时间/频率交织；
- CRC 驱动的帧接纳、序号驱动的去重和重排；
- 限幅/blanking、窄带 notch 或动态子带排除，但必须以 capture 验证；
- AGC 与手动增益对 near-far 的 A/B 测试；
- 丢帧后快速重新捕获，而不是让同步器长期锁死；
- 每种 modulation/coding profile 使用明确 ID，避免盲猜。

### 需要测量后决定

- 单载波与 OFDM：OFDM 有多径均衡和子载波避让优势，但 CFO、峰均比、同步及窄带/脉冲干扰行为更复杂。
- BPSK/QPSK 与高阶 QAM：计分是正确字节量，高阶调制只有在实际净吞吐提高时才有价值。
- 重复发送与更强 FEC：比较总占空时间内的正确唯一字节，不只比较单帧 PER。
- 固定频率与频率捷变：只有规程明确允许且收发双方无需禁用的侧信道协调时采用。
- 学习型分类器：只用离线保存的模型和确定性 fallback；记录置信度和错误选择成本。

### 不要默认采用

- 把 802.11、LoRa 或其他现成协议当作必然最优；其同步和编码值得参考，但固定开销/规则可能不匹配。
- 用无限 cyclic buffer 反复发相同数据；这会浪费计分时间并增加失控发射风险。
- 把滤波器标称名称当作竞赛允许频段。
- 依赖发射端与接收端之间的 Wi-Fi/Ethernet/串口反馈。

## 双电脑部署

### TX 电脑

- 预装冻结环境和 TX 程序。
- 只读取裁判 payload 和本地配置。
- 生成 manifest：payload SHA-256、chunk size、frame count、profile、随机化 seed。
- 显示发送进度、underflow、当前 frame/byte 和剩余时间。
- 提供本地键盘/进程停止，不依赖 RX 回传。

### RX 电脑

- 持续运行 acquisition，不等待 TX 侧握手。
- 原子写入已验证 frame，独立保存 packet log。
- 根据序号在内存/磁盘去重并重组。
- 周期性 flush，崩溃后不破坏已有正确数据。
- 实时显示 detected/header/FEC/CRC/unique-byte counters 和 overflow。

### 共同要求

- 使用相同版本的 profile 描述文件，但不依赖赛中同步修改。
- 让程序从冷启动自动发现指定 serial/URI 并 fail closed。
- 禁止自动选择“第一台设备”后立刻发射。
- 将日志写到本机，不发送到云或另一台电脑。

## 实验矩阵与验收

每个 profile 至少跑以下矩阵：

| 维度 | 样例水平 |
|---|---|
| SNR/SIR | clean、moderate、threshold、failure |
| CFO | 0、正/负小偏、捕获边界 |
| SRO | 0、典型晶振偏差、加倍压力值 |
| 增益 | manual 多档、slow AGC、fast AGC（若可用） |
| 干扰 | none、tone、burst、partial-band、co-channel |
| 包长 | 短、中、最大 |
| 运行时间 | 单帧、1 分钟、整轮时长、2 倍整轮 soak |
| 冷启动 | 第一次 USB 枚举、断开重连、程序崩溃恢复 |

验收门槛：

1. clean simulation 必须逐字节一致；
2. 固定 IQ capture 必须重复得到相同输出；
3. 没有合法 header/CRC 的数据不得进入裁判输出；
4. 出现 overflow/underflow 必须计数并在结果中标红；
5. 关闭非 SDR 接口后可从冷启动完成整个流程；
6. 紧急停止后设备不再处于 cyclic TX；
7. 整轮时长内没有无界内存增长、文件损坏或线程死锁。

## 常见错误

- 只看星座图漂亮，不统计正确唯一字节/秒。
- 在 RX 中频繁分配大数组导致丢样。
- 未记录 complex sample 的格式、字节序和缩放。
- TX/RX 的 bit order、FEC puncturing、interleaver 和 whitening seed 不一致。
- header 没有独立 CRC 或保护不足。
- 频偏估计只覆盖仿真值，真实振荡器超出捕获范围。
- AGC 在强 burst 干扰后恢复过慢。
- decoder 出错后没有重置内部同步/均衡状态。
- 把重复帧写入输出，造成有效字节统计虚高但裁判不认可。
- 赛前没有真正断网/禁用蓝牙进行离线演练。

