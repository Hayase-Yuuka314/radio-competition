# 用户操作手册

## 重要声明

**本项目当前是算法仿真与教学基线平台，不是可直接上场的 SDR 比赛系统。**

- 09/10 号脚本在 `--sim` 模式下只做 IQ 文件读写，不是无线传输。
- 去掉 `--sim` 后**不会**连接真实 SDR 发射——该路径仅有占位注释。
- 141 项自动测试覆盖算法单元，**不含** operation 比赛脚本。
- 吞吐率按波形样本数估算，**不代表真实空口速率**。

## 文件清单

| 文件 | 用途 | 实际能力 |
|---|---|---|
| `00_check.py` | 环境检查 | ✅ 依赖+冒烟测试 |
| `01_train_ml.py` | 训练ML模型 | ✅ 合成数据训练 (~90%准确率) |
| `02_use_ml.py` | ML推理演示 | ✅ 合成数据演示，非现场策略 |
| `03_simulate.py` | 传统通信仿真 | ✅ 纯软件闭环 |
| `04_dsss_demo.py` | DSSS对抗演示 | ✅ SNR=-10dB可用(仿真) |
| `05_visualize.py` | 生成全部图表 | ✅ 7张PNG |
| `06_contest.py` | 多队对抗分析 | ✅ 合成场景 |
| `07_all.py` | 一键运行00-06 | ✅ |
| `08_prepare.py` | 赛前准备清单 | ⚠️ 不检查真实SDR连接 |
| `09_contest_tx.py` | 发射端 | ⚠️ `--sim`=保存npy，无`--sim`=占位 |
| `10_contest_rx.py` | 接收端 | ⚠️ `--sim`=读取npy，无`--sim`=占位 |
| `11_contest_e2e.py` | 一条龙演练 | ✅ 纯软件仿真闭环 |

## 赛前可用操作

```bash
cd "C:\Users\16839\Desktop\无线电 - 副本"

# 环境检查
python operation/00_check.py

# 训练ML模型（合成数据）
python operation/01_train_ml.py

# 离线仿真对比
python operation/11_contest_e2e.py --size 5000 --mode dsss --snr 10
python operation/11_contest_e2e.py --size 5000 --mode robust --snr 20

# 生成图表
python operation/05_visualize.py
```

## 比赛现场不可用

- **不要** 去掉 `--sim` 期待 SDR 发射（代码未实现）
- **不要** 把脚本显示的吞吐率当成空口速率
- **不要** 使用默认频率/增益进行空口发射
- **不要** 把 ML 分类器作为现场自动策略（训练数据为合成）
- **不要** 直接提交 `recovered.bin`——先验证 SHA-256 与原始文件一致

## 达到可参赛状态前的最低修复

1. 实现 pyadi-iio 真实 SDR 收发驱动
2. 实现连续 IQ 流帧检测与同步
3. 填写并冻结 RF 参数（频点/带宽/功率）
4. 同轴线缆+衰减器完成两机实测
5. 采集真实 IQ 重新评估 ML
6. 增加硬件在环和性能测试
7. 连续运行 ≥ 比赛时长 2 倍
