"""干扰特征提取器。

从 IQ 信号中提取时域、频域和接收机侧特征，
用于训练干扰分类器（随机森林）。

特征设计原则：
  - 数学定义明确，单位和窗口可配置
  - 对采样率和窗长依赖已文档化
  - 缺失值策略：NaN/Inf → 0
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from scipy import signal as sp_signal


class FeatureExtractor:
    """多域特征提取器。

    对固定窗长的 IQ 信号提取特征向量。
    """

    def __init__(
        self,
        window_samples: int = 1024,
        sample_rate_hz: float = 2.0e6,
        n_spectral_bins: int = 16,
    ):
        """
        Args:
            window_samples: 分析窗长（采样点数）。
            sample_rate_hz: 采样率。
            n_spectral_bins: 频域子带数量。
        """
        self.window_samples = window_samples
        self.sample_rate_hz = sample_rate_hz
        self.n_spectral_bins = n_spectral_bins
        self._feature_names: list[str] = []

    # ── 时域特征 ──────────────────────────────────────────

    def _time_features(self, iq: np.ndarray) -> dict[str, float]:
        """提取时域特征。"""
        real = np.real(iq)
        imag = np.imag(iq)
        mag = np.abs(iq)
        phase = np.angle(iq)

        feats = {}

        # 功率
        power = float(np.mean(mag ** 2))
        feats["power"] = _safe(power)
        feats["rms"] = _safe(np.sqrt(power))

        # 实部/虚部统计
        feats["real_mean"] = _safe(float(np.mean(real)))
        feats["real_var"] = _safe(float(np.var(real)))
        feats["imag_mean"] = _safe(float(np.mean(imag)))
        feats["imag_var"] = _safe(float(np.var(imag)))

        # 幅度统计
        feats["mag_mean"] = _safe(float(np.mean(mag)))
        feats["mag_var"] = _safe(float(np.var(mag)))
        feats["mag_skew"] = _safe(_skewness(mag))
        feats["mag_kurt"] = _safe(_kurtosis(mag))

        # 峰均比
        peak = float(np.max(mag))
        feats["papr"] = _safe(peak / (np.sqrt(power) + 1e-12))

        # 过零率（实部符号变化率）
        sign_changes = np.sum(np.abs(np.diff(np.sign(real)))) / 2
        feats["zero_crossing_rate"] = _safe(sign_changes / len(real))

        # 削顶比例
        clip_thresh = 3 * np.std(real)
        feats["clipping_ratio"] = _safe(float(np.mean(np.abs(real) > clip_thresh)))

        # 包络自相关峰
        if len(mag) > 2:
            ac = np.correlate(mag - np.mean(mag), mag - np.mean(mag), mode="same")
            ac = ac / (ac[len(ac) // 2] + 1e-12)
            # 找第一旁瓣
            mid = len(ac) // 2
            sidemask = np.ones(len(ac), dtype=bool)
            sidemask[mid - 5 : mid + 5] = False
            if np.any(sidemask):
                feats["env_ac_peak"] = _safe(float(np.max(np.abs(ac[sidemask]))))
            else:
                feats["env_ac_peak"] = 0.0
        else:
            feats["env_ac_peak"] = 0.0

        # 相位差方差（衡量频率稳定性）
        if len(phase) > 1:
            feats["phase_diff_var"] = _safe(float(np.var(np.diff(phase))))
        else:
            feats["phase_diff_var"] = 0.0

        return feats

    # ── 频域特征 ──────────────────────────────────────────

    def _freq_features(self, iq: np.ndarray) -> dict[str, float]:
        """提取频域特征（基于 Welch PSD）。"""
        feats = {}

        # Welch PSD
        nperseg = min(256, len(iq) // 4)
        if nperseg < 8:
            # 信号太短，降级为 FFT
            fft = np.fft.fftshift(np.fft.fft(iq))
            psd = np.abs(fft) ** 2
        else:
            f, psd = sp_signal.welch(iq, fs=self.sample_rate_hz,
                                     nperseg=nperseg, return_onesided=False)

        psd = np.asarray(psd, dtype=np.float64)
        total_power = float(np.sum(psd)) + 1e-12

        # 归一化 PSD
        psd_norm = psd / total_power

        # 总功率
        feats["total_power"] = _safe(float(np.log10(total_power + 1)))

        # 子带功率
        n_bins = self.n_spectral_bins
        bin_edges = np.linspace(0, len(psd), n_bins + 1, dtype=int)
        for i in range(n_bins):
            sub_power = float(np.sum(psd[bin_edges[i] : bin_edges[i + 1]]))
            feats[f"subband_power_{i}"] = _safe(sub_power / total_power)

        # 最大谱峰
        feats["max_peak_height"] = _safe(float(np.max(psd_norm)))
        feats["max_peak_location"] = _safe(float(np.argmax(psd_norm)) / len(psd_norm))

        # 前 3 个谱峰间距
        peak_indices = _find_peaks_simple(psd_norm, min_height=0.01, min_distance=3)
        for i, idx in enumerate(peak_indices[:3]):
            feats[f"peak_{i}_location"] = _safe(float(idx) / len(psd_norm))
        if len(peak_indices) >= 2:
            feats["peak_spacing_mean"] = _safe(float(np.mean(np.diff(peak_indices[:3]))))
        else:
            feats["peak_spacing_mean"] = 0.0

        # 频谱质心
        indices = np.arange(len(psd_norm))
        centroid = float(np.sum(indices * psd_norm))
        feats["spectral_centroid"] = _safe(centroid / len(psd_norm))

        # 频谱平坦度（Wiener 熵）
        geo_mean = np.exp(np.mean(np.log(psd_norm + 1e-12)))
        ari_mean = np.mean(psd_norm) + 1e-12
        feats["spectral_flatness"] = _safe(geo_mean / ari_mean)

        # 频谱熵
        feats["spectral_entropy"] = _safe(-float(np.sum(psd_norm * np.log(psd_norm + 1e-12))))

        # 带边功率比
        edge_frac = 0.1
        n_edge = max(1, int(len(psd) * edge_frac))
        center_start = n_edge
        center_end = len(psd) - n_edge
        edge_power = float(np.sum(psd[:n_edge]) + np.sum(psd[center_end:]))
        center_power = float(np.sum(psd[center_start:center_end])) + 1e-12
        feats["edge_center_power_ratio"] = _safe(edge_power / center_power)

        # 窄带峰数量
        n_peaks = len(_find_peaks_simple(psd_norm, min_height=0.05, min_distance=5))
        feats["narrowband_peak_count"] = float(n_peaks)

        return feats

    # ── 接收机特征 ────────────────────────────────────────

    def _rx_features(
        self,
        iq: np.ndarray,
        rx_snr_db: float = float("nan"),
        rx_evm: float = float("nan"),
        rx_cfo_hz: float = float("nan"),
        rx_per: float = float("nan"),
        rx_goodput_bps: float = float("nan"),
    ) -> dict[str, float]:
        """提取接收机侧特征（来自 RX pipeline 的输出）。"""
        return {
            "rx_snr_db": _safe(rx_snr_db),
            "rx_evm": _safe(rx_evm),
            "rx_cfo_hz": _safe(rx_cfo_hz),
            "rx_per": _safe(rx_per),
            "rx_goodput_bps": _safe(rx_goodput_bps),
        }

    # ── 总接口 ────────────────────────────────────────────

    def extract(
        self,
        iq: np.ndarray,
        rx_snr_db: float = float("nan"),
        rx_evm: float = float("nan"),
        rx_cfo_hz: float = float("nan"),
        rx_per: float = float("nan"),
        rx_goodput_bps: float = float("nan"),
    ) -> np.ndarray:
        """提取完整特征向量。

        Args:
            iq: IQ 信号（复数数组），长度应匹配 window_samples。
            rx_snr_db 等: 可选的接收机侧指标。

        Returns:
            一维 float64 特征向量。
        """
        # 确保长度一致（截断或补零）
        iq_proc = np.asarray(iq, dtype=np.complex128).flatten()
        if len(iq_proc) < self.window_samples:
            iq_proc = np.pad(iq_proc, (0, self.window_samples - len(iq_proc)))
        else:
            iq_proc = iq_proc[:self.window_samples]

        features: dict[str, float] = {}
        features.update(self._time_features(iq_proc))
        features.update(self._freq_features(iq_proc))
        features.update(self._rx_features(
            iq_proc, rx_snr_db, rx_evm, rx_cfo_hz, rx_per, rx_goodput_bps
        ))

        # 缓存特征名（仅第一次）
        if not self._feature_names:
            self._feature_names = sorted(features.keys())

        # 按固定顺序输出
        vec = np.array([features.get(k, 0.0) for k in self._feature_names],
                       dtype=np.float64)
        return vec

    @property
    def feature_names(self) -> list[str]:
        """特征名称列表（需先调用 extract 一次以初始化）。"""
        if not self._feature_names:
            # 提供一个默认的特征向量触发初始化
            dummy = np.zeros(self.window_samples, dtype=np.complex128)
            self.extract(dummy)
        return self._feature_names

    @property
    def n_features(self) -> int:
        return len(self.feature_names)


# ── 辅助函数 ───────────────────────────────────────────────

def _safe(x: float) -> float:
    """将 NaN/Inf 转为 0。"""
    if np.isnan(x) or np.isinf(x):
        return 0.0
    return float(x)


def _skewness(x: np.ndarray) -> float:
    """偏度。"""
    x = np.asarray(x, dtype=np.float64)
    m = np.mean(x)
    s = np.std(x)
    if s < 1e-12:
        return 0.0
    return float(np.mean(((x - m) / s) ** 3))


def _kurtosis(x: np.ndarray) -> float:
    """峰度（excess kurtosis）。"""
    x = np.asarray(x, dtype=np.float64)
    m = np.mean(x)
    s = np.std(x)
    if s < 1e-12:
        return 0.0
    return float(np.mean(((x - m) / s) ** 4) - 3.0)


def _find_peaks_simple(
    x: np.ndarray,
    min_height: float = 0.0,
    min_distance: int = 1,
) -> np.ndarray:
    """简单峰值检测（不依赖 scipy.signal.find_peaks 版本兼容性）。"""
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    if n < 3:
        return np.array([], dtype=int)

    # 找局部最大
    peaks = []
    for i in range(1, n - 1):
        if x[i] > x[i - 1] and x[i] > x[i + 1] and x[i] > min_height:
            peaks.append(i)

    if not peaks:
        return np.array([], dtype=int)

    # 按高度排序，然后按最小距离过滤
    peaks = np.array(peaks)
    heights = x[peaks]
    order = np.argsort(-heights)
    kept = []
    for idx in order:
        p = peaks[idx]
        if all(abs(p - k) >= min_distance for k in kept):
            kept.append(p)
    return np.array(sorted(kept), dtype=int)
