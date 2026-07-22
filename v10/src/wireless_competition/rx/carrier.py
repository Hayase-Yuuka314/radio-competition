"""载波相位跟踪。

使用 Costas 环跟踪残余相位偏移。
"""

from __future__ import annotations

import numpy as np


class CostasLoop:
    """Costas 环：BPSK/QPSK 载波相位跟踪。

    BPSK: 使用 real(s) * imag(s) 作为误差
    QPSK: 使用 sign(real) * imag - sign(imag) * real
    """

    def __init__(self, loop_bandwidth: float = 0.01, is_qpsk: bool = False):
        self.loop_bw = loop_bandwidth
        self.is_qpsk = is_qpsk
        self._phase = 0.0
        self._freq = 0.0

    def reset(self):
        self._phase = 0.0
        self._freq = 0.0

    def process(self, symbol: complex) -> complex:
        """处理一个符号，返回相位校正后的符号。"""
        # 相位旋转
        corrected = symbol * np.exp(-1j * self._phase)

        # 计算误差
        if self.is_qpsk:
            error = (np.sign(np.real(corrected)) * np.imag(corrected)
                     - np.sign(np.imag(corrected)) * np.real(corrected))
        else:
            # BPSK
            error = np.real(corrected) * np.imag(corrected)

        # 环路滤波器
        self._freq += self.loop_bw * error
        self._phase += self._freq + self.loop_bw * error

        # 相位归一到 [-pi, pi)
        self._phase = np.angle(np.exp(1j * self._phase))

        return corrected

    def process_batch(self, symbols: np.ndarray) -> np.ndarray:
        """批量处理符号。"""
        result = np.zeros(len(symbols), dtype=np.complex128)
        for i, s in enumerate(symbols):
            result[i] = self.process(s)
        return result
