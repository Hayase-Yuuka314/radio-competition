"""符号定时恢复模块。

使用 Gardner 算法实现符号定时同步。
"""

from __future__ import annotations

import numpy as np


class GardnerTimingRecovery:
    """Gardner 定时误差检测器 + 插值。

    适用于 BPSK/QPSK，每符号至少 2 个采样点。
    """

    def __init__(
        self,
        samples_per_symbol: int = 8,
        damping: float = 0.707,
        loop_bandwidth: float = 0.01,
    ):
        if samples_per_symbol < 2:
            raise ValueError("Gardner requires samples_per_symbol >= 2")

        self.sps = samples_per_symbol
        self.damping = damping
        self.loop_bw = loop_bandwidth

        # 二阶环路滤波器系数
        theta = loop_bandwidth / (damping + 1 / (4 * damping))
        d = 1 + 2 * damping * theta + theta ** 2
        self.kp = 4 * damping * theta / d
        self.ki = 4 * theta ** 2 / d

        self._reset()

    def _reset(self):
        """重置内部状态。"""
        self._mu = 0.0            # 分数间隔
        self._phase_error = 0.0   # 积分项
        self._prev_mid = 0.0 + 0j
        self._prev_symbol = 0.0 + 0j

    def process(self, iq_signal: np.ndarray) -> np.ndarray:
        """从过采样 IQ 恢复符号。

        Args:
            iq_signal: 过采样 IQ 波形。

        Returns:
            符号率复数数组。
        """
        self._reset()
        n = len(iq_signal)
        symbols = []
        idx = 0

        while idx + 2 * self.sps <= n:
            # Gardner 需要连续 3 个 strobe 点
            # strobe 在 mu + k*sps 处

            # 简单实现：每个 sps 间隔取一个符号
            if idx + self.sps <= n:
                # 线性插值
                base = idx + int(self._mu * self.sps)
                if base + 1 < n:
                    frac = self._mu
                    sample = (1 - frac) * iq_signal[base] + frac * iq_signal[base + 1]
                else:
                    sample = iq_signal[min(base, n - 1)]

                # 中点样本（两个 strobe 之间的中心）
                mid_base = base + self.sps // 2
                if mid_base + 1 < n:
                    mid_sample = (1 - frac) * iq_signal[mid_base] + frac * iq_signal[min(mid_base + 1, n - 1)]
                else:
                    mid_sample = iq_signal[min(mid_base, n - 1)]

                # Gardner TED
                if self._prev_mid != 0:
                    error = np.real(
                        (self._prev_symbol - sample) * np.conj(self._prev_mid)
                    )
                else:
                    error = 0.0

                symbols.append(sample)

                # 更新环路
                self._phase_error += self.ki * error
                correction = self.kp * error + self._phase_error
                self._mu += 1.0 / self.sps + correction
                # 确保 mu 在 [0, 1)
                while self._mu >= 1.0:
                    self._mu -= 1.0
                    idx += self.sps
                while self._mu < 0:
                    self._mu += 1.0

                self._prev_mid = mid_sample
                self._prev_symbol = sample
            else:
                idx += self.sps

        return np.array(symbols, dtype=np.complex128)


def symbol_timing_by_correlation(
    iq_signal: np.ndarray,
    preamble: np.ndarray,
    samples_per_symbol: int,
) -> tuple[np.ndarray, int]:
    """通过前导相关找到最佳定时偏移并输出符号。

    Args:
        iq_signal: 接收 IQ 波形。
        preamble: 前导符号。
        samples_per_symbol: 每符号采样数。

    Returns:
        (符号率 IQ, 最佳定时偏移采样数)。
    """
    preamble_n = len(preamble)

    # 尝试各定时偏移
    best_offset = 0
    best_corr = -1.0

    for offset in range(samples_per_symbol):
        sym = iq_signal[offset::samples_per_symbol][:preamble_n]
        if len(sym) < preamble_n:
            break
        corr = np.abs(np.correlate(sym, preamble.conj()))
        peak = np.max(corr)
        if peak > best_corr:
            best_corr = peak
            best_offset = offset

    symbols = iq_signal[best_offset::samples_per_symbol]
    return symbols, best_offset
