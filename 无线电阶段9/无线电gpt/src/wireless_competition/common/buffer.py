"""环形缓冲区 + 健康监控。

线程安全的环形缓冲区，用于 SDR 采集与 DSP 处理解耦。
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class BufferStats:
    """缓冲区统计。"""
    capacity: int = 0
    current_depth: int = 0
    high_water_mark: int = 0
    total_written: int = 0
    total_read: int = 0
    dropped_samples: int = 0
    overflow_count: int = 0
    underflow_count: int = 0
    last_write_time: float = 0.0
    last_read_time: float = 0.0


class RingBuffer:
    """线程安全环形缓冲区。

    策略：
      - 写入时若满 → 覆盖旧数据（记录丢样数）
      - 读取时若空 → 返回空数组（记录 underflow）
      - 高水位告警：current_depth > capacity * 0.7
    """

    def __init__(self, capacity: int = 32768, dtype=np.complex64):
        """
        Args:
            capacity: 最大样本数。
            dtype: 存储数据类型。
        """
        self._capacity = capacity
        self._buf = np.zeros(capacity, dtype=dtype)
        self._write_pos = 0
        self._read_pos = 0
        self._lock = threading.RLock()  # 可重入锁

        self.stats = BufferStats(capacity=capacity)

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def available(self) -> int:
        """可读取的样本数。"""
        with self._lock:
            if self._write_pos >= self._read_pos:
                return self._write_pos - self._read_pos
            else:
                return self._capacity - self._read_pos + self._write_pos

    @property
    def free(self) -> int:
        """可写入的空间。"""
        return self._capacity - self.available - 1

    def write(self, data: np.ndarray) -> int:
        """写入样本。返回实际写入数。"""
        data = np.asarray(data, dtype=self._buf.dtype).flatten()
        n = len(data)

        with self._lock:
            if n == 0:
                return 0

            avail = self.available
            free_space = self._capacity - avail - 1

            if n > free_space:
                # 覆盖：丢弃被覆盖的旧数据
                overflow = n - free_space
                self._read_pos = (self._read_pos + overflow) % self._capacity
                self.stats.dropped_samples += overflow
                self.stats.overflow_count += 1

            # 环形写入
            end_pos = self._write_pos + n
            if end_pos <= self._capacity:
                self._buf[self._write_pos:end_pos] = data
            else:
                first_chunk = self._capacity - self._write_pos
                self._buf[self._write_pos:] = data[:first_chunk]
                self._buf[:end_pos - self._capacity] = data[first_chunk:]

            self._write_pos = end_pos % self._capacity
            self.stats.total_written += n
            self.stats.last_write_time = time.time()

            # 更新水位
            depth = self.available
            self.stats.current_depth = depth
            if depth > self.stats.high_water_mark:
                self.stats.high_water_mark = depth

        return n

    def read(self, n: int) -> np.ndarray:
        """读取最多 n 个样本。返回实际读到的数据。"""
        with self._lock:
            avail = self.available
            if avail == 0:
                self.stats.underflow_count += 1
                return np.array([], dtype=self._buf.dtype)

            n = min(n, avail)
            result = np.zeros(n, dtype=self._buf.dtype)

            end_pos = self._read_pos + n
            if end_pos <= self._capacity:
                result[:] = self._buf[self._read_pos:end_pos]
            else:
                first_chunk = self._capacity - self._read_pos
                result[:first_chunk] = self._buf[self._read_pos:]
                result[first_chunk:] = self._buf[:end_pos - self._capacity]

            self._read_pos = end_pos % self._capacity
            self.stats.total_read += n
            self.stats.last_read_time = time.time()
            self.stats.current_depth = self.available

        return result

    def is_high_water(self, threshold: float = 0.7) -> bool:
        """是否超过高水位线。"""
        return self.available > int(self._capacity * threshold)

    def reset(self):
        """清空缓冲区并重置统计。"""
        with self._lock:
            self._write_pos = 0
            self._read_pos = 0
            self.stats = BufferStats(capacity=self._capacity)


@dataclass
class HealthStatus:
    """系统健康状态。"""
    device_connected: bool = False
    device_uri: str = ""
    last_sample_time: float = 0.0
    buffer_depth: int = 0
    dropped_samples: int = 0
    center_frequency_hz: float = 0.0
    sample_rate_hz: float = 0.0
    gain_db: float = 0.0
    sync_state: str = "idle"
    snr_estimate_db: float = float("nan")
    evm: float = float("nan")
    per: float = 0.0
    goodput_bps: float = 0.0
    profile_active: str = ""
    ml_prediction: str = ""
    ml_confidence: float = 0.0
    is_ood: bool = False
    blocks_recovered: int = 0
    total_blocks: int = 0
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    disk_free_gb: float = 0.0
    recent_errors: list[str] = field(default_factory=list)


class HealthMonitor:
    """健康监控器。收集并格式化系统运行状态。"""

    def __init__(self, buffer: Optional[RingBuffer] = None):
        self._buffer = buffer
        self._status = HealthStatus()
        self._start_time = time.time()

    def update(
        self,
        device_connected: Optional[bool] = None,
        snr_db: Optional[float] = None,
        evm: Optional[float] = None,
        per: Optional[float] = None,
        goodput: Optional[float] = None,
        sync_state: Optional[str] = None,
        profile: Optional[str] = None,
        ml_pred: Optional[str] = None,
        ml_conf: Optional[float] = None,
        is_ood: Optional[bool] = None,
        blocks_recovered: Optional[int] = None,
        total_blocks: Optional[int] = None,
        error: Optional[str] = None,
    ):
        """更新监控状态。"""
        s = self._status
        if device_connected is not None:
            s.device_connected = device_connected
        if snr_db is not None:
            s.snr_estimate_db = snr_db
        if evm is not None:
            s.evm = evm
        if per is not None:
            s.per = per
        if goodput is not None:
            s.goodput_bps = goodput
        if sync_state is not None:
            s.sync_state = sync_state
        if profile is not None:
            s.profile_active = profile
        if ml_pred is not None:
            s.ml_prediction = ml_pred
        if ml_conf is not None:
            s.ml_confidence = ml_conf
        if is_ood is not None:
            s.is_ood = is_ood
        if blocks_recovered is not None:
            s.blocks_recovered = blocks_recovered
        if total_blocks is not None:
            s.total_blocks = total_blocks

        if self._buffer is not None:
            s.buffer_depth = self._buffer.available
            s.dropped_samples = self._buffer.stats.dropped_samples
            s.last_sample_time = self._buffer.stats.last_write_time

        if error:
            s.recent_errors.append(f"{time.strftime('%H:%M:%S')} {error}")
            if len(s.recent_errors) > 20:  # 只保留最近 20 条
                s.recent_errors = s.recent_errors[-20:]

    def summary(self) -> dict:
        """返回可序列化的状态摘要。"""
        s = self._status
        return {
            "uptime_s": time.time() - self._start_time,
            "device_connected": s.device_connected,
            "buffer_depth": s.buffer_depth,
            "dropped_samples": s.dropped_samples,
            "sync_state": s.sync_state,
            "snr_db": s.snr_estimate_db,
            "evm": s.evm,
            "per": s.per,
            "goodput_bps": s.goodput_bps,
            "profile": s.profile_active,
            "ml_prediction": s.ml_prediction,
            "ml_confidence": s.ml_confidence,
            "is_ood": s.is_ood,
            "blocks": f"{s.blocks_recovered}/{s.total_blocks}",
            "recent_errors": s.recent_errors[-5:],
        }

    def is_healthy(self) -> tuple[bool, list[str]]:
        """健康检查。返回 (是否健康, 问题列表)。"""
        issues = []
        s = self._status
        if not s.device_connected:
            issues.append("SDR not connected")
        if s.dropped_samples > 100:
            issues.append(f"Samples dropped: {s.dropped_samples}")
        if s.buffer_depth > 30000:
            issues.append(f"Buffer nearly full: {s.buffer_depth}")
        return len(issues) == 0, issues
