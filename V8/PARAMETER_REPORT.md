# 参数报告 — 发送给队友

> 包含：GNU Radio 测试流图参数 + Python 比赛系统参数 + 使用步骤

---

## 一、GNU Radio 测试流图（硬件验证用）

这是两个 `.grc` 文件，用 GNU Radio Companion 打开。

### TX: `little_test.grc` — 文件 → BPSK → PlutoSDR 发射

```
test_data.txt → [BPSK调制+差分编码+RRC] → ×0.7 → PlutoSDR
```

| 参数 | 值 | 说明 | 可调？ |
|---|---|---|---|
| `samp_rate` | 1e6 | 采样率 1Msps | 可，TX/RX 必须一致 |
| `center_freq` | 433e6 | 433MHz ISM 频段 | 可，用滤波器对应频段 |
| `sps` | 4 | 每符号采样数 | TX/RX 必须一致 |
| `alpha` | 0.35 | RRC 滚降因子 | TX/RX 必须一致 |
| `tx_attenuation` | 10 | 发射衰减 (0=max, 89=min) | 可，信号太强就加大 |
| `constellation` | BPSK + 差分编码 | 抗相位模糊 | 不能用 QPSK |
| `multiply_const` | 0.7 | 幅度缩放 | 0.5~1.0 |
| `file` | `test_data.txt` | 要发的文件，循环发射 | 改成你的文件名 |

### RX: `little_test_rx.grc` — PlutoSDR 接收 → 解调 → 文件

```
PlutoSDR → AGC → FLL → Skip1s → 符号同步 → Costas → 差分解码 → rx_output.txt
```

| 参数 | 值 | 说明 | 可调？ |
|---|---|---|---|
| `samp_rate` | 1e6 | 必须和 TX 一致 | --- |
| `center_freq` | 433e6 | 必须和 TX 一致 | --- |
| `sps` | 4 | 必须和 TX 一致 | --- |
| `alpha` | 0.35 | 必须和 TX 一致 | --- |
| `rx_gain` | 40 | 0~70，信号弱可提高 | 可 |
| `nfilts` | 32 | 同步精度/速度平衡 | 16~64 |
| `skiphead` | 1e6 (1秒) | 跳过锁定前数据 | 0.5~2 秒 |

### 启动步骤

1. 两个 PlutoSDR USB 都插上
2. 两个电脑都打开 Radioconda 里的 GNU Radio Companion
3. 分别打开 `little_test.grc` 和 `little_test_rx.grc`
4. **先启动 RX**（按 F6 或点 Run）→ **再启动 TX**
5. 比较 `test_data.txt` 和 `rx_output.txt` 是否一致

---

## 二、Python 比赛系统（正式比赛用）

### 核心链路

```
原始文件
  → [Fountain Encoder] 喷泉码分块（无需 ACK）
    → [DSSS Encoder] Gold 码扩频 SF=128（21dB 处理增益）
      → [TDD MAC] CCA 信道检测 → TX 时隙发射
        → PlutoSDR TX（接 2.4GHz 滤波器）~~~~ 空中 ~~~~
          → PlutoSDR RX（无滤波器）
        ← [TDD MAC] RX 时隙接收
      ← [DSSS Decoder] 前导搜索 → 解扩 → 喷泉包提取
    ← [Fountain Decoder] 收够 K+5% 包 → 解码
  → 恢复文件
```

### 比赛发射命令

```bash
# 先激活环境
$env:PATH = "C:\Users\86186\radioconda;C:\Users\86186\radioconda\Library\bin;C:\Users\86186\radioconda\Scripts;" + $env:PATH
$env:PYTHONPATH = "C:\Users\86186\Desktop\hit\src"

# 仿真测试（不需 SDR，确认代码正常）
python -m wireless_competition.cli.transmit input.bin --team-id 0 --sim --sim-snr 20 --output recovered.bin

# 实机发射（TX 电脑）
python -m wireless_competition.cli.transmit input.bin --team-id 0 --freq 2450e6

# 实机接收（RX 电脑）
python -m wireless_competition.cli.receive --team-id 0 --freq 2450e6 --output recovered.bin
```

### 发射参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--team-id` | 0 | 队伍编号。不同队不同值，对应不同 Gold 码 |
| `--freq` | 2450e6 | 中心频率 (Hz)。比赛用 2.4GHz 频段 |
| `--sample-rate` | 2.0e6 | 采样率 (Hz)。对应 2MHz 带宽 |
| `--spreading-factor` | 128 | DSSS 扩频因子。128→21dB 处理增益 |
| `--block-size` | 256 | 喷泉码块大小 (bytes) |
| `--tx-gain` | -10.0 | 发射增益 (dB) |
| `--sim` | off | 仿真模式（无硬件） |
| `--sim-snr` | 20.0 | 仿真信噪比 (dB) |
| `--output` | 无 | 输出文件路径 |

### 接收参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--team-id` | 0 | 必须和发射端一致 |
| `--rx-uri` | ip:192.168.2.2 | RX SDR 地址 |
| `--freq` | 2450e6 | 必须和发射端一致 |
| `--rx-gain` | 40.0 | 接收增益 (dB) |
| `--output` | recovered_team0.bin | 恢复的文件 |

---

## 三、射频连接方案（仅 1 个滤波器）

```
TX 链路（有滤波器）：
  PlutoSDR TX → [2.4GHz 带通滤波器] → 2.4GHz 吸盘天线 (垂直极化)

RX 链路（无滤波器，靠 TDD 保护）：
  2.4GHz 吸盘天线 (水平极化) → PlutoSDR RX
```

| 保护措施 | 说明 |
|---|---|
| 正交极化 | TX 垂直、RX 水平 → 额外 ~20dB 隔离 |
| 天线距离 | 拉开 2m 以上 |
| TDD 时序 | TX 和 RX 永不同时工作 |
| RX 增益回退 | TX 时隙 RX 增益降至最低保护前端 |

**433MHz 频段作为备用**：如果现场 2.4GHz WiFi 干扰严重，切换到 433MHz。

---

## 四、检查清单（比赛前）

- [ ] 两个 PlutoSDR USB 都能被电脑识别（绿灯亮）
- [ ] GNU Radio 测试流图收发 OK（文件一致）
- [ ] Python 仿真测试通过（`--sim` 模式）
- [ ] 2.4GHz 滤波器接在 **TX** SDR 上
- [ ] 两个天线正交极化（一个垂直、一个水平）
- [ ] 笔记本关闭 WiFi / 蓝牙 / 所有其他无线
- [ ] 电源插排备好
- [ ] `team-id` 全队统一（选一个 0~15 的值）
