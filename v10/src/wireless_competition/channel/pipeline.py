"""信道流水线。

组合 AWGN、硬件损伤、多径和干扰，保持独立开关和有序施加。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np

from ..common.types import ChannelConfig, ChannelOutput
from .awgn import add_awgn
from .impairments import (
    apply_cfo,
    apply_clipping,
    apply_dc_offset,
    apply_drop_samples,
    apply_iq_imbalance,
    apply_phase_noise,
    apply_quantization,
    apply_sro,
    apply_timing_offset,
)
from .interference import generate_interference
from .multipath import apply_multipath


class ChannelPipeline:
    """信道流水线：按固定顺序施加各种损伤。"""

    def __init__(self, config: ChannelConfig = ChannelConfig()):
        self.config = config

    def apply(
        self,
        iq: np.ndarray,
        sample_rate_hz: float,
        rng: np.random.Generator,
        config: ChannelConfig | None = None,
    ) -> ChannelOutput:
        """施加全部启用损伤。

        施加顺序：
          1. AWGN
          2. 多径
          3. CFO
          4. 定时偏移
          5. 相位噪声
          6. DC 偏移
          7. IQ 不平衡
          8. 削顶
          9. 干扰
          10. 量化
          11. 丢样

        Args:
            iq: 输入复数 IQ。
            sample_rate_hz: 采样率。
            rng: 随机数生成器。
            config: 可选覆盖配置。

        Returns:
            ChannelOutput 包含处理后 IQ 和真值标签。
        """
        cfg = config if config is not None else self.config
        result = iq.copy().astype(np.complex128)

        signal_power = np.mean(np.abs(iq) ** 2)
        events: dict[str, Any] = {}

        # 1. AWGN
        if cfg.enable_awgn:
            result = add_awgn(result, cfg.snr_db, signal_power, rng)

        # 2. 多径
        if cfg.enable_multipath and cfg.channel_taps:
            result = apply_multipath(result, cfg.channel_taps)

        # 3. CFO
        if abs(cfg.cfo_hz) > 1e-9:
            result = apply_cfo(result, cfg.cfo_hz, sample_rate_hz)

        # 4. 定时偏移
        if abs(cfg.timing_offset_symbols) > 1e-9:
            result = apply_timing_offset(result, cfg.timing_offset_symbols, 1)  # sps=1 时在符号域操作

        # 5. 相位噪声
        if cfg.enable_phase_noise and cfg.phase_noise_std_rad > 0:
            result = apply_phase_noise(result, cfg.phase_noise_std_rad, rng)

        # 6. DC 偏移
        if cfg.enable_dc_offset:
            result = apply_dc_offset(result, cfg.dc_offset)

        # 7. IQ 不平衡
        if cfg.enable_iq_imbalance:
            result = apply_iq_imbalance(
                result, cfg.iq_gain_imbalance_db, cfg.iq_phase_imbalance_deg
            )

        # 8. 削顶
        if cfg.enable_clipping:
            result = apply_clipping(result, cfg.clipping_threshold)

        # 9. 干扰
        if cfg.enable_interference:
            interference = generate_interference(
                n_samples=len(result),
                sample_rate_hz=sample_rate_hz,
                interference_type=cfg.interference_type.value,
                inr_db=cfg.inr_db,
                signal_power=signal_power,
                rng=rng,
            )
            result = result + interference

        # 10. 量化
        if cfg.enable_quantization:
            result = apply_quantization(result, cfg.quantization_bits)

        # 11. 丢样
        if cfg.enable_drop_samples and cfg.drop_probability > 0:
            result, drop_mask = apply_drop_samples(result, cfg.drop_probability, rng)
            events["dropped_samples"] = int(np.sum(drop_mask))

        # 12. 固定增益
        if cfg.gain_db != 0:
            gain_linear = 10 ** (cfg.gain_db / 20)
            result = result * gain_linear

        # 计算实际 SNR (用于真值标签)
        post_signal = np.mean(np.abs(result) ** 2)
        noise_estimate = signal_power / (10 ** (cfg.snr_db / 10)) if cfg.snr_db < 100 else 0

        # 配置哈希
        config_hash_val = hashlib.sha256(
            json.dumps(cfg.__dict__, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]

        return ChannelOutput(
            iq=result.astype(np.complex64),
            sample_rate_hz=sample_rate_hz,
            ground_truth_snr_db=cfg.snr_db,
            ground_truth_inr_db=cfg.inr_db if cfg.enable_interference else -100.0,
            ground_truth_cfo_hz=cfg.cfo_hz,
            ground_truth_timing_offset=cfg.timing_offset_symbols,
            ground_truth_channel_taps=list(cfg.channel_taps) if cfg.enable_multipath else [1.0+0j],
            events=events,
            seed=rng.bit_generator._seed_seq.entropy,  # best effort
            config_hash=config_hash_val,
        )
