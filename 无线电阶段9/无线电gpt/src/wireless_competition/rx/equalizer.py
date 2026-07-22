"""自适应均衡器。

LMS (最小均方) 均衡器，支持训练模式和判决引导模式。
用于对抗多径效应和码间干扰。
"""

from __future__ import annotations

from typing import Optional

import numpy as np


class LMSEqualizer:
    """LMS 自适应均衡器。

    前馈均衡器结构：y[n] = sum(w[k] * x[n-k])。
    权重更新：w[k] += mu * error * conj(x[n-k])。
    """

    def __init__(
        self,
        n_taps: int = 16,
        step_size: float = 0.01,
        training_mode: bool = True,
    ):
        """
        Args:
            n_taps: 均衡器抽头数。
            step_size: LMS 步长 (mu)，越大收敛越快但稳态误差越大。
            training_mode: True=训练模式(需参考信号), False=判决引导。
        """
        self.n_taps = n_taps
        self.mu = step_size
        self.training_mode = training_mode

        # 权重初始化为中间抽头为 1（无滤波）
        self._weights = np.zeros(n_taps, dtype=np.complex128)
        self._weights[n_taps // 2] = 1.0 + 0j

        # 内部缓冲（延迟线）
        self._delay_line = np.zeros(n_taps, dtype=np.complex128)

    def reset(self):
        """重置均衡器状态。"""
        self._weights = np.zeros(self.n_taps, dtype=np.complex128)
        self._weights[self.n_taps // 2] = 1.0 + 0j
        self._delay_line = np.zeros(self.n_taps, dtype=np.complex128)

    def equalize(
        self,
        input_signal: np.ndarray,
        training_signal: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """均衡一段信号。

        Args:
            input_signal: 输入复数信号。
            training_signal: 训练序列（训练模式时必需）。

        Returns:
            均衡后的信号。
        """
        n = len(input_signal)
        output = np.zeros(n, dtype=np.complex128)

        for i in range(n):
            # 移位延迟线
            self._delay_line[1:] = self._delay_line[:-1]
            self._delay_line[0] = input_signal[i]

            # 滤波
            y = np.dot(self._weights, self._delay_line)

            # 误差计算
            if self.training_mode and training_signal is not None and i < len(training_signal):
                desired = training_signal[i]
            else:
                # 判决引导：硬判为最近星座点
                desired = self._decision(y)

            error = desired - y

            # LMS 更新
            self._weights += self.mu * error * np.conj(self._delay_line)

            output[i] = y

        return output

    def equalize_batch(
        self,
        input_signal: np.ndarray,
        training_signal: Optional[np.ndarray] = None,
        train_length: int = 100,
    ) -> np.ndarray:
        """批量均衡（训练前 train_length 个符号，然后切换判决引导）。"""
        n = len(input_signal)
        output = np.zeros(n, dtype=np.complex128)

        for i in range(n):
            self._delay_line[1:] = self._delay_line[:-1]
            self._delay_line[0] = input_signal[i]

            y = np.dot(self._weights, self._delay_line)

            # 前 train_length 个符号用训练，之后判决引导
            if i < train_length and training_signal is not None and i < len(training_signal):
                desired = training_signal[i]
                error = desired - y
                self._weights += self.mu * error * np.conj(self._delay_line)
            elif i >= train_length:
                desired = self._decision(y)
                error = desired - y
                self._weights += self.mu * 0.5 * error * np.conj(self._delay_line)  # 减速

            output[i] = y

        return output

    @staticmethod
    def _decision(symbol: complex) -> complex:
        """BPSK/QPSK 硬判决。"""
        real = np.sign(np.real(symbol))
        imag = np.sign(np.imag(symbol))
        return (real + 1j * imag) / np.sqrt(2) if abs(imag) > 0.1 else real + 0j

    @property
    def weights(self) -> np.ndarray:
        return self._weights.copy()
