"""帧检测器。

通过前导相关实现帧检测和粗定时估计。
"""

from __future__ import annotations

import numpy as np

from ..tx.framing import make_preamble, make_sync_word


class FrameDetector:
    """基于前导相关的帧检测器。

    在符号率（匹配滤波后）上进行检测。
    """

    def __init__(
        self,
        preamble: np.ndarray | None = None,
        sync_word: np.ndarray | None = None,
        detection_threshold: float = 0.5,
        samples_per_symbol: int = 8,
        preamble_length_symbols: int = 64,
    ):
        if preamble is None:
            preamble = make_preamble(samples_per_symbol, preamble_length_symbols, "pn")
        if sync_word is None:
            sync_word = make_sync_word()

        self.preamble = np.asarray(preamble, dtype=np.complex128)
        self.sync_word = np.asarray(sync_word, dtype=np.complex128)
        self.threshold = detection_threshold
        self.sps = samples_per_symbol
        self.preamble_len = len(self.preamble)
        self._preamble_energy = np.sum(np.abs(self.preamble) ** 2)

        # 预计算脉冲成形后的前导（用于采样率检测）
        from ..tx.pulse_shaping import pulse_shape
        self.preamble_shaped = pulse_shape(self.preamble, samples_per_symbol, 0.35, 6)
        self._shaped_energy = np.sum(np.abs(self.preamble_shaped) ** 2)

    def correlate_symbol_rate(self, symbols: np.ndarray) -> np.ndarray:
        """在符号率上计算归一化相关。

        Args:
            symbols: 符号率复数数组（匹配滤波+下采样后）。

        Returns:
            归一化相关系数。
        """
        if len(symbols) < self.preamble_len:
            return np.zeros(len(symbols), dtype=np.float64)

        # 滑动窗口功率
        power = np.abs(symbols) ** 2
        cumsum = np.concatenate([[0], np.cumsum(power)])
        window_power = cumsum[self.preamble_len:] - cumsum[:-self.preamble_len]

        # 互相关
        corr = np.abs(np.correlate(symbols, self.preamble.conj(), mode='valid'))

        denom = np.sqrt(window_power * self._preamble_energy)
        norm = np.zeros(len(symbols), dtype=np.float64)
        valid_len = len(corr)
        start = self.preamble_len - 1
        norm[start:start + valid_len] = np.divide(
            corr, denom, out=np.zeros(valid_len), where=denom > 1e-12
        )
        return norm

    def correlate(self, iq_signal: np.ndarray) -> np.ndarray:
        """在过采样 IQ 上计算归一化相关（使用脉冲成形前导）。

        Args:
            iq_signal: 过采样 IQ 信号。

        Returns:
            归一化相关系数。
        """
        window_size = len(self.preamble_shaped)
        if len(iq_signal) < window_size:
            return np.zeros(len(iq_signal), dtype=np.float64)

        power = np.abs(iq_signal) ** 2
        cumsum = np.concatenate([[0], np.cumsum(power)])
        window_power = cumsum[window_size:] - cumsum[:-window_size]

        corr = np.abs(np.correlate(iq_signal, self.preamble_shaped.conj(), mode='valid'))
        denom = np.sqrt(window_power * self._shaped_energy)
        norm = np.zeros(len(iq_signal), dtype=np.float64)
        valid_len = len(corr)
        start = window_size - 1
        norm[start:start + valid_len] = np.divide(
            corr, denom, out=np.zeros(valid_len), where=denom > 1e-12
        )
        return norm

    def detect(
        self,
        iq_signal: np.ndarray,
        min_distance_sym: int = 0,
    ) -> list[int]:
        """检测帧起始位置（符号级索引）。

        在过采样 IQ 上先匹配滤波，再在符号率检测。

        Args:
            iq_signal: 接收 IQ 波形（过采样）。
            min_distance_sym: 两次检测间最小符号距离。

        Returns:
            符号级起始索引列表（前导开始符号位置）。
        """
        # 先做匹配滤波 + 下采样
        from ..tx.pulse_shaping import matched_filter as mf_func
        mf_iq = mf_func(iq_signal, self.sps, 0.35, 6)

        # 选择最佳定时偏移
        from .timing import symbol_timing_by_correlation
        symbols, _ = symbol_timing_by_correlation(mf_iq, self.preamble, self.sps)

        # 在符号率上相关
        corr = self.correlate_symbol_rate(symbols)

        if min_distance_sym <= 0:
            min_distance_sym = self.preamble_len // 2

        peaks = []
        i = 0
        n = len(corr)
        while i < n:
            if corr[i] > self.threshold:
                j = i
                while j + 1 < n - min_distance_sym and corr[j + 1] > corr[j]:
                    j += 1
                peak_pos = j
                start_pos = max(0, peak_pos - self.preamble_len + 1)
                peaks.append(start_pos)
                i = j + min_distance_sym
            else:
                i += 1

        return peaks

    def refine_timing(
        self,
        iq_signal: np.ndarray,
        coarse_start: int,
    ) -> int:
        """在前导检测基础上精细定时。

        Args:
            iq_signal: 接收 IQ 波形。
            coarse_start: 粗检测帧起始位置。

        Returns:
            精细化的帧起始位置。
        """
        # 在粗位置附近搜索同步字
        search_win = self.preamble_len // 2
        start = max(0, coarse_start - search_win)
        end = min(len(iq_signal), coarse_start + search_win + len(self.sync_word))
        if end <= start:
            return coarse_start

        region = iq_signal[start:end]
        sync_corr = np.correlate(region, self.sync_word.conj(), mode='valid')
        if len(sync_corr) == 0:
            return coarse_start

        peak_offset = int(np.argmax(np.abs(sync_corr)))
        return start + peak_offset
