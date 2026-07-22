"""干扰数据集生成器。

从信道仿真器批量生成带标签的 IQ 样本，
按 capture_id 分组划分防止数据泄漏。
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Optional

import numpy as np

from ..channel.pipeline import ChannelPipeline
from ..common.seeds import create_seed_sequence
from ..common.types import ChannelConfig, InterferenceFamily
from ..features.time_domain import FeatureExtractor


# 干扰类型 → 信道配置的映射
INTERFERENCE_CONFIGS: dict[str, dict] = {
    "clean": {
        "enable_interference": False,
        "interference_type": "clean",
        "inr_db": -100.0,
    },
    "tone": {
        "enable_interference": True,
        "interference_type": "tone",
        "inr_db": 10.0,
    },
    "multitone": {
        "enable_interference": True,
        "interference_type": "multitone",
        "inr_db": 10.0,
    },
    "sweep": {
        "enable_interference": True,
        "interference_type": "sweep",
        "inr_db": 10.0,
    },
    "broadband_noise": {
        "enable_interference": True,
        "interference_type": "broadband_noise",
        "inr_db": 10.0,
    },
    "bandlimited_noise": {
        "enable_interference": True,
        "interference_type": "bandlimited_noise",
        "inr_db": 10.0,
    },
    "burst": {
        "enable_interference": True,
        "interference_type": "burst",
        "inr_db": 15.0,
    },
}


class InterferenceDataset:
    """干扰数据集。

    每个样本包含：
      - 特征向量 (np.ndarray)
      - 干扰标签 (str)
      - capture_id (分组划分用)
      - scenario_id
      - 元数据 (SNR, INR, CFO 等)
    """

    def __init__(
        self,
        feature_extractor: Optional[FeatureExtractor] = None,
        n_features: Optional[int] = None,
    ):
        self.extractor = feature_extractor or FeatureExtractor()
        self._features: list[np.ndarray] = []
        self._labels: list[str] = []
        self._capture_ids: list[str] = []
        self._metadata: list[dict] = []

    def add_samples(
        self,
        features: np.ndarray,
        labels: list[str],
        capture_id: str,
        metadata_list: Optional[list[dict]] = None,
    ) -> None:
        """添加一批样本。"""
        n = len(labels)
        self._features.extend([features[i] for i in range(n)])
        self._labels.extend(labels)
        self._capture_ids.extend([capture_id] * n)
        if metadata_list:
            self._metadata.extend(metadata_list)
        else:
            self._metadata.extend([{}] * n)

    @property
    def X(self) -> np.ndarray:
        return np.array(self._features, dtype=np.float64)

    @property
    def y(self) -> np.ndarray:
        return np.array(self._labels)

    @property
    def capture_ids(self) -> np.ndarray:
        return np.array(self._capture_ids)

    @property
    def unique_labels(self) -> list[str]:
        return sorted(set(self._labels))

    @property
    def n_samples(self) -> int:
        return len(self._labels)

    def split_by_capture(
        self,
        train_frac: float = 0.6,
        val_frac: float = 0.2,
        test_frac: float = 0.2,
        seed: int = 42,
    ) -> tuple["InterferenceDataset", "InterferenceDataset", "InterferenceDataset"]:
        """按 capture_id 分组划分（防止同一次采集泄漏到不同集合）。

        Returns:
            (train, val, test) 三个子集。
        """
        rng = np.random.default_rng(seed)
        unique_captures = sorted(set(self._capture_ids))
        rng.shuffle(unique_captures)

        n = len(unique_captures)
        n_train = max(1, int(n * train_frac))
        n_val = max(1, int(n * val_frac))

        train_caps = set(unique_captures[:n_train])
        val_caps = set(unique_captures[n_train : n_train + n_val])
        test_caps = set(unique_captures[n_train + n_val:])

        def _subset(capture_set):
            ds = InterferenceDataset(
                feature_extractor=self.extractor,
            )
            for i in range(self.n_samples):
                if self._capture_ids[i] in capture_set:
                    ds._features.append(self._features[i])
                    ds._labels.append(self._labels[i])
                    ds._capture_ids.append(self._capture_ids[i])
                    ds._metadata.append(self._metadata[i])
            return ds

        return _subset(train_caps), _subset(val_caps), _subset(test_caps)


def generate_dataset(
    n_captures_per_class: int = 30,
    n_windows_per_capture: int = 20,
    window_samples: int = 1024,
    snr_db_range: list[float] | None = None,
    sample_rate_hz: float = 2.0e6,
    seed: int = 42,
    progress: bool = False,
) -> InterferenceDataset:
    """从仿真生成完整的干扰数据集。

    Args:
        n_captures_per_class: 每种干扰类型的采集次数。
        n_windows_per_capture: 每次采集滑窗截取的样本数。
        window_samples: 分析窗长。
        snr_db_range: SNR 范围（随机均匀抽取）。
        sample_rate_hz: 采样率。
        seed: 基础种子。
        progress: 是否打印进度。

    Returns:
        InterferenceDataset 实例。
    """
    if snr_db_range is None:
        snr_db_range = [-5, 0, 5, 10, 20]

    rng = np.random.default_rng(seed)
    extractor = FeatureExtractor(window_samples=window_samples,
                                 sample_rate_hz=sample_rate_hz)
    dataset = InterferenceDataset(feature_extractor=extractor)

    # 预先生成 BPSK 符号作为"期望信号"
    from ..tx.modulation import bpsk_modulate
    base_symbols = bpsk_modulate((rng.random(window_samples * 4) > 0.5).astype(np.uint8))
    base_iq = base_symbols.astype(np.complex128)

    class_names = sorted(INTERFERENCE_CONFIGS.keys())
    capture_seeds = create_seed_sequence(n_captures_per_class * len(class_names), seed)

    for cls_idx, class_name in enumerate(class_names):
        cfg_dict = INTERFERENCE_CONFIGS[class_name]

        for cap_idx in range(n_captures_per_class):
            idx = cls_idx * n_captures_per_class + cap_idx
            cap_seed = capture_seeds[idx]
            cap_rng = np.random.default_rng(cap_seed)

            # 随机选 SNR
            snr_db = float(cap_rng.choice(snr_db_range))

            # 随机选 CFO
            cfo_hz = cap_rng.uniform(-500, 500)

            capture_id = f"{class_name}_{cap_idx:04d}_s{cap_seed}"

            channel = ChannelPipeline(ChannelConfig(
                snr_db=snr_db,
                cfo_hz=cfo_hz,
                enable_interference=cfg_dict["enable_interference"],
                interference_type=InterferenceFamily(cfg_dict["interference_type"]),
                inr_db=float(cfg_dict.get("inr_db", 10.0)),
            ))

            # 生成一段长 IQ → 滑窗切分
            total_samples = window_samples * (n_windows_per_capture + 1)
            long_iq = np.tile(base_iq, total_samples // len(base_iq) + 1)[:total_samples]

            ch_out = channel.apply(long_iq, sample_rate_hz, cap_rng)
            noisy_iq = ch_out.iq

            # 滑窗提取
            for w in range(n_windows_per_capture):
                start = w * window_samples
                seg = noisy_iq[start : start + window_samples]
                feat = extractor.extract(seg, rx_snr_db=snr_db, rx_cfo_hz=cfo_hz)

                meta = {
                    "snr_db": snr_db,
                    "cfo_hz": cfo_hz,
                    "inr_db": cfg_dict.get("inr_db", -100),
                    "interference_type": class_name,
                    "capture_id": capture_id,
                    "window_idx": w,
                }

                dataset._features.append(feat)
                dataset._labels.append(class_name)
                dataset._capture_ids.append(capture_id)
                dataset._metadata.append(meta)

            if progress:
                print(f"  [{class_name}] capture {cap_idx+1}/{n_captures_per_class} done")

    return dataset
