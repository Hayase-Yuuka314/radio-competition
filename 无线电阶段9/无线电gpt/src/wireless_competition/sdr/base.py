"""SDR 硬件抽象接口。

所有上层算法只依赖此抽象接口。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol

import numpy as np

from ..common.types import DeviceHealth, RxHardwareConfig, TxHardwareConfig


class SDRDevice(ABC):
    """SDR 设备抽象基类。"""

    @abstractmethod
    def configure_rx(self, config: RxHardwareConfig) -> None:
        """配置接收参数。"""
        ...

    @abstractmethod
    def configure_tx(self, config: TxHardwareConfig) -> None:
        """配置发射参数。"""
        ...

    @abstractmethod
    def receive(self, num_samples: int) -> np.ndarray:
        """接收 IQ 样本。

        Args:
            num_samples: 请求样本数。

        Returns:
            复数 IQ 数组。
        """
        ...

    @abstractmethod
    def transmit(self, iq: np.ndarray) -> None:
        """发射 IQ 样本。"""
        ...

    @abstractmethod
    def health(self) -> DeviceHealth:
        """获取设备健康状态。"""
        ...


class SimulatedSDRDevice(SDRDevice):
    """纯软件仿真 SDR。

    用于离线开发和测试。
    """

    def __init__(self, sample_rate_hz: float = 2.0e6):
        self._sample_rate_hz = sample_rate_hz
        self._rx_buffer: np.ndarray = np.array([], dtype=np.complex64)
        self._rx_config: RxHardwareConfig | None = None
        self._tx_config: TxHardwareConfig | None = None

    def configure_rx(self, config: RxHardwareConfig) -> None:
        self._rx_config = config
        self._sample_rate_hz = config.sample_rate_hz

    def configure_tx(self, config: TxHardwareConfig) -> None:
        self._tx_config = config

    def receive(self, num_samples: int) -> np.ndarray:
        """从内部缓冲区取样本。"""
        if len(self._rx_buffer) == 0:
            return np.array([], dtype=np.complex64)
        n = min(num_samples, len(self._rx_buffer))
        result = self._rx_buffer[:n].copy()
        self._rx_buffer = self._rx_buffer[n:]
        return result

    def transmit(self, iq: np.ndarray) -> None:
        """将样本放入内部缓冲区（模拟发射→接收环回）。"""
        self._rx_buffer = np.concatenate([self._rx_buffer, iq.astype(np.complex64)])

    def health(self) -> DeviceHealth:
        return DeviceHealth(
            connected=True,
            uri="simulated://",
            buffer_depth=len(self._rx_buffer),
        )

    @property
    def sample_rate_hz(self) -> float:
        return self._sample_rate_hz


class FileReplaySDRDevice(SDRDevice):
    """从文件重放 IQ 记录。

    用于离线分析真实采集数据。
    """

    def __init__(self, iq_file: str = "", sample_rate_hz: float = 2.0e6):
        self._iq_file = iq_file
        self._sample_rate_hz = sample_rate_hz
        self._data: np.ndarray | None = None
        self._pos: int = 0

    def configure_rx(self, config: RxHardwareConfig) -> None:
        self._sample_rate_hz = config.sample_rate_hz

    def configure_tx(self, config: TxHardwareConfig) -> None:
        pass

    def load_iq(self, iq_data: np.ndarray) -> None:
        """加载 IQ 数据。"""
        self._data = iq_data.astype(np.complex64)
        self._pos = 0

    def receive(self, num_samples: int) -> np.ndarray:
        if self._data is None:
            return np.array([], dtype=np.complex64)
        end = min(self._pos + num_samples, len(self._data))
        result = self._data[self._pos:end].copy()
        self._pos = end
        return result

    def transmit(self, iq: np.ndarray) -> None:
        pass

    def health(self) -> DeviceHealth:
        return DeviceHealth(
            connected=self._data is not None,
            uri=f"file://{self._iq_file}",
        )
