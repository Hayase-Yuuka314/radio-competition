"""对抗通信模块。

基于 DSSS（直接序列扩频）的对抗性通信系统。

设计理念：
  - 己方正常扩频通信 = 对对手天然强干扰
  - 不规则帧结构 = 增加对手检测难度  
  - 动态策略 = 根据信道条件自适应调整
"""

from .dsss import (
    SpreadingCodeManager,
    spread,
    despread,
    despread_fft,
    generate_spreading_code,
    generate_gold_code,
    processing_gain_db,
)
from .waveform import AdversarialWaveform, FrameRandomizer
from .strategy import AdversarialController, AdversarialStrategy, StrategyLevel
from .evaluation import (
    evaluate_dsss_performance,
    evaluate_multiteam_interference,
)
