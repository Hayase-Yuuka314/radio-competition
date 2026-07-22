"""TDD MAC layer for competition.

Coordinates TX/RX timing, clear channel assessment (CCA), and frequency
hopping to enable reliable communication in a contested spectrum.

Design principles for single-filter constraint:
- TX SDR has the 2.4GHz filter → cleaner signal
- RX SDR is bare → needs TDD protection from own TX
- TX and RX never operate simultaneously
- CCA before TX to avoid collisions with other teams
- Frequency hopping to escape persistent interference
"""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto

import numpy as np


class SlotType(Enum):
    TX = "tx"
    RX = "rx"
    CCA = "cca"
    GUARD = "guard"


@dataclass
class TDDConfig:
    """TDD MAC configuration."""
    superframe_duration_s: float = 0.200
    cca_duration_s: float = 0.005
    tx_duration_s: float = 0.080
    rx_duration_s: float = 0.080
    guard_duration_s: float = 0.005

    cca_threshold_db: float = -70.0
    cca_backoff_min_s: float = 0.010
    cca_backoff_max_s: float = 0.100

    hop_channels_hz: list[float] = field(default_factory=lambda: [
        2.405e9, 2.410e9, 2.415e9, 2.420e9, 2.425e9,
        2.430e9, 2.435e9, 2.440e9, 2.445e9, 2.450e9,
        2.455e9, 2.460e9, 2.465e9, 2.470e9, 2.475e9,
        2.480e9,
    ])
    hop_interval_frames: int = 1
    channel_blacklist_duration_s: float = 5.0

    sample_rate_hz: float = 2.0e6

    def validate(self) -> list[str]:
        issues = []
        total = self.cca_duration_s + self.tx_duration_s + self.rx_duration_s + 3 * self.guard_duration_s
        if total > self.superframe_duration_s:
            issues.append(f"Slot durations ({total:.3f}s) exceed superframe ({self.superframe_duration_s:.3f}s)")
        return issues


@dataclass
class CCAReport:
    """Result of a clear channel assessment."""
    channel_free: bool
    measured_power_db: float
    channel_frequency_hz: float
    timestamp_s: float
    details: dict = field(default_factory=dict)


class FrequencyHopper:
    """Manages frequency hopping sequence with channel blacklisting."""

    def __init__(self, channels_hz: list[float], hop_interval: int = 1,
                 blacklist_timeout_s: float = 5.0):
        self._channels = list(channels_hz)
        self._hop_interval = hop_interval
        self._blacklist_timeout_s = blacklist_timeout_s

        self._current_index = 0
        self._frame_count = 0
        self._blacklist: dict[float, float] = {}

    @property
    def current(self) -> float:
        return self._channels[self._current_index % len(self._channels)]

    @property
    def num_channels(self) -> int:
        return len(self._channels)

    def blacklist_current(self):
        """Blacklist current channel for timeout duration."""
        now = time.monotonic()
        self._blacklist[self.current] = now + self._blacklist_timeout_s

    def _clean_blacklist(self):
        now = time.monotonic()
        expired = [ch for ch, t in self._blacklist.items() if now >= t]
        for ch in expired:
            del self._blacklist[ch]

    def next(self) -> float:
        """Advance to next channel, skipping blacklisted ones."""
        self._clean_blacklist()
        self._frame_count += 1

        if self._frame_count % self._hop_interval == 0:
            attempts = 0
            while attempts < len(self._channels):
                self._current_index = (self._current_index + 1) % len(self._channels)
                if self._channels[self._current_index] not in self._blacklist:
                    break
                attempts += 1

        return self.current

    def skip_channel(self):
        """Immediately skip current channel (e.g., detected heavy interference)."""
        for _ in range(min(3, len(self._channels))):
            self._current_index = (self._current_index + 1) % len(self._channels)
            if self._channels[self._current_index] not in self._blacklist:
                break

    @property
    def active_channels(self) -> list[float]:
        """Return currently non-blacklisted channels."""
        self._clean_blacklist()
        return [ch for ch in self._channels if ch not in self._blacklist]


class TDDController:
    """TDD MAC controller for coordinating TX/RX timing.

    Manages the superframe-based timing schedule:
      [CCA] [GUARD] [TX] [GUARD] [RX] [GUARD]

    During CCA: Sense channel power, if channel is free → proceed to TX
    During TX:  TX SDR transmits, RX SDR is disabled
    During RX:  RX SDR receives, TX SDR is silent
    During GUARD: Both silent (transient settling)

    Usage:
        tdd = TDDController(config)
        tdd.start_superframe()
        while contest_running:
            if tdd.current_slot == SlotType.CCA:
                power = rx_sdr.measure_power()
                if power < tdd.config.cca_threshold_db:
                    tdd.advance_slot()
                else:
                    tdd.backoff()
            elif tdd.current_slot == SlotType.TX:
                tx_sdr.transmit(next_buffer)
                tdd.advance_slot()
            elif tdd.current_slot == SlotType.RX:
                data = rx_sdr.receive(buf_size)
                process(data)
                tdd.advance_slot()
    """

    def __init__(self, config: TDDConfig):
        self.config = config
        self._hopper = FrequencyHopper(
            config.hop_channels_hz,
            config.hop_interval_frames,
            config.channel_blacklist_duration_s,
        )

        self._current_slot: SlotType = SlotType.GUARD
        self._slot_start_time: float = 0.0
        self._superframe_count: int = 0
        self._cca_power_history: deque = deque(maxlen=32)

        self._slot_durations: dict[SlotType, float] = {
            SlotType.CCA: config.cca_duration_s,
            SlotType.TX: config.tx_duration_s,
            SlotType.RX: config.rx_duration_s,
            SlotType.GUARD: config.guard_duration_s,
        }

        self._slot_order = [
            (SlotType.CCA, SlotType.CCA),
            (SlotType.CCA, SlotType.GUARD),
            (SlotType.GUARD, SlotType.TX),
            (SlotType.TX, SlotType.GUARD),
            (SlotType.GUARD, SlotType.RX),
            (SlotType.RX, SlotType.GUARD),
        ]

        self._slot_idx: int = 0
        self._channel_occupied: bool = False
        self._backoff_until: float = 0.0

        self._stats = {
            "tx_slots": 0,
            "rx_slots": 0,
            "cca_blocks": 0,
            "channel_busy_count": 0,
            "hops": 0,
        }

    @property
    def current_slot(self) -> SlotType:
        return self._current_slot

    @property
    def current_frequency(self) -> float:
        return self._hopper.current

    @property
    def stats(self) -> dict:
        return dict(self._stats)

    def slot_duration(self, slot_type: SlotType) -> float:
        return self._slot_durations.get(slot_type, 0.0)

    def remaining_slot_time(self) -> float:
        elapsed = time.monotonic() - self._slot_start_time
        remaining = self.slot_duration(self._current_slot) - elapsed
        return max(0.0, remaining)

    def start_superframe(self):
        """Begin a new TDD superframe."""
        self._slot_start_time = time.monotonic()
        self._superframe_count += 1
        self._slot_idx = 0
        self._current_slot = SlotType.CCA

    def advance_slot(self) -> SlotType:
        """Move to next slot in the TDD sequence. Returns new slot type."""
        wait_for = self.remaining_slot_time()
        if wait_for > 1e-6:
            time.sleep(wait_for)

        if self._backoff_until > time.monotonic():
            time.sleep(self._backoff_until - time.monotonic())
            self._backoff_until = 0

        self._slot_idx += 1
        if self._slot_idx >= len(self._slot_order):
            self._slot_idx = 0
            self._hopper.next()
            self._stats["hops"] += 1

        effective_slot = self._slot_order[self._slot_idx][1]
        self._current_slot = effective_slot
        self._slot_start_time = time.monotonic()

        if effective_slot == SlotType.TX:
            self._stats["tx_slots"] += 1
        elif effective_slot == SlotType.RX:
            self._stats["rx_slots"] += 1

        return effective_slot

    def perform_cca(self, measured_power_db: float) -> CCAReport:
        """Evaluate CCA based on measured channel power.

        Args:
            measured_power_db: measured RF power in dBm (or relative dB).

        Returns:
            CCAReport with channel assessment.
        """
        self._cca_power_history.append(measured_power_db)
        threshold = self.config.cca_threshold_db
        channel_free = measured_power_db < threshold

        if not channel_free:
            self._stats["channel_busy_count"] += 1
            self._channel_occupied = True
        else:
            self._stats["cca_blocks"] += 1
            self._channel_occupied = False

        return CCAReport(
            channel_free=channel_free,
            measured_power_db=measured_power_db,
            channel_frequency_hz=self._hopper.current,
            timestamp_s=time.monotonic(),
            details={
                "threshold_db": threshold,
                "history_mean_db": float(np.mean(self._cca_power_history))
                if self._cca_power_history else float("nan"),
                "history_std_db": float(np.std(self._cca_power_history))
                if self._cca_power_history else float("nan"),
            },
        )

    def backoff(self):
        """Back off when channel is occupied. Blacklist channel if persistent."""
        now = time.monotonic()
        consecutive_busy = sum(
            1 for p in list(self._cca_power_history)[-8:]
            if p >= self.config.cca_threshold_db
        )

        if consecutive_busy >= 5:
            self._hopper.blacklist_current()
            self._hopper.skip_channel()

        backoff_duration = np.random.uniform(
            self.config.cca_backoff_min_s,
            self.config.cca_backoff_max_s * (1 + consecutive_busy * 0.5),
        )
        self._backoff_until = now + backoff_duration

    def is_channel_free(self) -> bool:
        return not self._channel_occupied

    def measure_channel_power(self, iq_samples: np.ndarray) -> float:
        """Estimate channel power from IQ samples (in dB relative to full scale).

        Uses the average power of the input IQ samples.
        """
        if len(iq_samples) == 0:
            return -100.0
        power_linear = np.mean(np.abs(iq_samples) ** 2)
        if power_linear < 1e-20:
            return -100.0
        return float(10.0 * math.log10(power_linear))


def create_competition_tdd_config(team_id: int = 0) -> TDDConfig:
    """Create a TDD config tuned for the competition scenario.

    Staggers the superframe start times slightly per team to reduce
    collision probability at CCA boundaries.
    """
    channels = [
        2.405e9 + i * 5e6 for i in range(16)
    ]
    np.random.seed(42 + team_id * 100)
    np.random.shuffle(channels)

    return TDDConfig(
        superframe_duration_s=0.200,
        cca_duration_s=0.005,
        tx_duration_s=0.080,
        rx_duration_s=0.080,
        guard_duration_s=0.005,
        cca_threshold_db=-70.0,
        hop_channels_hz=channels,
        channel_blacklist_duration_s=5.0,
    )
