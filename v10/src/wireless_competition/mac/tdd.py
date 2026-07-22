"""Competition TDD MAC — Fountain-optimised.

Key design:
  - TX/RX are separate SDRs → need TDD to avoid self-interference
  - Fountain codes need no ACK → TX can be aggressive, no RX-gated retransmit
  - CCA is optional (teams expected to transmit; polite mode available)
  - Frequency hopping with channel quality tracking + exponential backoff
"""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np


class SlotType(Enum):
    CCA = "cca"
    TX = "tx"
    RX = "rx"
    GUARD = "guard"
    IDLE = "idle"


class CCAMode(Enum):
    OFF = "off"
    ENERGY_DETECT = "energy"
    CORRELATION = "corr"


@dataclass
class TDDConfig:
    """TDD MAC configuration."""
    # Superframe slot durations
    cca_duration_s: float = 0.003
    tx_duration_s: float = 0.070
    rx_duration_s: float = 0.040
    guard_duration_s: float = 0.005

    # CCA
    cca_mode: CCAMode = CCAMode.ENERGY_DETECT
    cca_threshold_db: float = -65.0
    cca_samples: int = 4096
    cca_min_window_s: float = 0.001
    cca_backoff_base_s: float = 0.010
    cca_backoff_max_s: float = 0.320
    cca_max_retries: int = 4
    cca_blacklist_after: int = 5

    # Frequency hopping
    hop_channels_hz: list[float] = field(default_factory=lambda: [
        2.405e9 + i * 5e6 for i in range(16)
    ])
    hop_interval_frames: int = 2
    hop_channel_dwell_min: int = 1
    hop_channel_dwell_max: int = 8
    channel_blacklist_s: float = 10.0
    channel_quality_window: int = 64

    sample_rate_hz: float = 2.0e6

    def validate(self) -> list[str]:
        issues = []
        slots = self.cca_duration_s + self.tx_duration_s + self.rx_duration_s
        guards = 3 * self.guard_duration_s
        if slots + guards > 0.500:
            issues.append(f"Frame too long: {slots + guards:.3f}s > 500ms")
        if self.tx_duration_s < 0.010:
            issues.append(f"TX slot too short: {self.tx_duration_s * 1000:.0f}ms")
        if self.rx_duration_s < 0.010:
            issues.append(f"RX slot too short: {self.rx_duration_s * 1000:.0f}ms")
        return issues


@dataclass
class CCAReport:
    channel_free: bool
    power_db: float
    freq_hz: float
    timestamp_s: float
    retry_count: int = 0
    extra: dict = field(default_factory=dict)


@dataclass
class SuperframeStats:
    frame_id: int = 0
    freq_hz: float = 0.0
    slot: str = ""
    tx_packets: int = 0
    rx_packets: int = 0
    cca_free: bool = True
    cca_power_db: float = -100.0
    backoff_ms: float = 0.0
    goodput_bps: float = 0.0
    timestamp_s: float = 0.0


class ChannelQualityTracker:
    """Track per-channel quality via packet success rate."""

    def __init__(self, window: int = 64):
        self._window = window
        self._history: dict[float, deque] = {}

    def record(self, freq_hz: float, packets_ok: int, packets_total: int):
        dq = self._history.setdefault(freq_hz, deque(maxlen=self._window))
        dq.append(1 if packets_total > 0 and packets_ok >= packets_total * 0.8 else 0)

    def score(self, freq_hz: float) -> float:
        dq = self._history.get(freq_hz, deque())
        if not dq:
            return 0.5
        return sum(dq) / len(dq)

    def best_channels(self, n: int = 4) -> list[float]:
        chs = [(f, self.score(f)) for f in self._history if self.score(f) > 0.4]
        chs.sort(key=lambda x: -x[1])
        return [c[0] for c in chs[:n]]


class FrequencyHopper:
    """Frequency hopper with quality-aware channel selection + blacklisting."""

    def __init__(self, channels: list[float], blacklist_s: float = 10.0):
        self._channels = list(channels)
        self._blacklist: dict[float, float] = {}
        self._blacklist_timeout = blacklist_s
        self._index = 0
        self._frames = 0
        self.quality = ChannelQualityTracker()

    @property
    def current(self) -> float:
        return self._channels[self._index % len(self._channels)]

    def _clean(self):
        now = time.monotonic()
        for ch in list(self._blacklist):
            if now >= self._blacklist[ch]:
                del self._blacklist[ch]

    def blacklist(self, freq: float):
        self._blacklist[freq] = time.monotonic() + self._blacklist_timeout

    def _available(self) -> list[int]:
        self._clean()
        return [i for i, ch in enumerate(self._channels) if ch not in self._blacklist]

    def next(self) -> float:
        self._frames += 1
        available = self._available()
        if not available:
            return self.current

        # Prefer high-quality channels
        best = self.quality.best_channels(4)
        high_quality = [i for i, ch in enumerate(self._channels)
                        if ch in best and i in available]
        candidates = high_quality if high_quality else available

        self._index = candidates[self._frames % len(candidates)]
        return self.current

    def force_hop(self):
        available = self._available()
        if available:
            self._index = available[np.random.randint(0, len(available))]

    @property
    def num_available(self) -> int:
        return len(self._available())


class ExponentialBackoff:
    """CSMA/CA-style exponential backoff."""

    def __init__(self, base_s: float = 0.010, max_s: float = 0.320, max_retries: int = 4):
        self._base = base_s
        self._max = max_s
        self._max_retries = max_retries
        self._retries = 0

    def next(self) -> Optional[float]:
        if self._retries >= self._max_retries:
            return None
        slot = np.random.randint(0, 2 ** self._retries)
        delay = min(slot * self._base, self._max)
        self._retries += 1
        return delay

    def reset(self):
        self._retries = 0

    @property
    def exhausted(self) -> bool:
        return self._retries >= self._max_retries

    @property
    def retries(self) -> int:
        return self._retries


class TDDController:
    """Competition TDD MAC.

    Superframe: [CCA?] [TX] [GUARD] [RX] [GUARD]

    Fountain-optimised:
      - No-ACK mode: TX bursts fountain packets without waiting for RX gating
      - RX is best-effort: collects whatever comes in during RX window
      - CCA optional; when enabled, uses exponential backoff
      - Channels ranked by packet success rate; poor channels blacklisted
    """

    def __init__(self, config: TDDConfig):
        self.cfg = config
        self._hopper = FrequencyHopper(config.hop_channels_hz, config.channel_blacklist_s)
        self._backoff = ExponentialBackoff(
            config.cca_backoff_base_s, config.cca_backoff_max_s, config.cca_max_retries,
        )

        self._slot: SlotType = SlotType.IDLE
        self._slot_start: float = 0.0
        self._frame_id: int = 0
        self._cca_power_window: deque = deque(maxlen=16)

        # Stage-based slot sequence
        self._stages = self._build_stages()
        self._stage_idx = 0

        # Stats
        self._tx_frames = 0
        self._rx_frames = 0
        self._cca_ok = 0
        self._cca_fail = 0
        self._hops = 0
        self._backoffs = 0
        self._frame_stats: list[SuperframeStats] = []

    def _build_stages(self) -> list[tuple[SlotType, SlotType]]:
        if self.cfg.cca_mode == CCAMode.OFF:
            return [
                (SlotType.IDLE, SlotType.TX),
                (SlotType.TX, SlotType.GUARD),
                (SlotType.GUARD, SlotType.RX),
                (SlotType.RX, SlotType.GUARD),
            ]
        return [
            (SlotType.IDLE, SlotType.CCA),
            (SlotType.CCA, SlotType.GUARD),
            (SlotType.GUARD, SlotType.TX),
            (SlotType.TX, SlotType.GUARD),
            (SlotType.GUARD, SlotType.RX),
            (SlotType.RX, SlotType.GUARD),
        ]

    # -- properties --------------------------------------------------

    @property
    def slot(self) -> SlotType:
        return self._slot

    # Backward-compat aliases
    @property
    def current_slot(self) -> SlotType:
        return self._slot

    @property
    def frequency(self) -> float:
        return self._hopper.current

    @property
    def current_frequency(self) -> float:
        return self._hopper.current

    @property
    def frame_id(self) -> int:
        return self._frame_id

    @property
    def stats(self) -> dict:
        return {
            "frame": self._frame_id,
            "tx_frames": self._tx_frames,
            "rx_frames": self._rx_frames,
            "cca_ok": self._cca_ok,
            "cca_fail": self._cca_fail,
            "hops": self._hops,
            "backoffs": self._backoffs,
            "channels_available": self._hopper.num_available,
        }

    def slot_duration(self, st: SlotType) -> float:
        return {
            SlotType.CCA: self.cfg.cca_duration_s,
            SlotType.TX: self.cfg.tx_duration_s,
            SlotType.RX: self.cfg.rx_duration_s,
            SlotType.GUARD: self.cfg.guard_duration_s,
            SlotType.IDLE: 0.0,
        }.get(st, 0.0)

    def remaining(self) -> float:
        return max(0.0, self.slot_duration(self._slot) - (time.monotonic() - self._slot_start))

    # -- frame control ------------------------------------------------

    def start_frame(self):
        self._frame_id += 1
        self._stage_idx = 0
        self._slot = SlotType.TX if self.cfg.cca_mode == CCAMode.OFF else SlotType.CCA
        self._slot_start = time.monotonic()
        self._backoff.reset()

    # Backward-compat aliases
    start_superframe = start_frame

    def _hop_if_needed(self):
        if self._frame_id % self.cfg.hop_interval_frames == 0:
            self._hopper.next()
            self._hops += 1

    def advance(self) -> SlotType:
        """Finish current slot and move to next. Returns new slot type."""
        rem = self.remaining()
        if rem > 1e-6:
            time.sleep(rem)

        self._stage_idx += 1
        if self._stage_idx >= len(self._stages):
            self._stage_idx = 0
            self._hop_if_needed()

        _, effective = self._stages[self._stage_idx]
        self._slot = effective
        self._slot_start = time.monotonic()

        if effective == SlotType.TX:
            self._tx_frames += 1
        elif effective == SlotType.RX:
            self._rx_frames += 1

        return effective

    # Backward-compat alias
    advance_slot = advance

    def skip_to(self, target: SlotType):
        """Skip to a specific slot (e.g., skip CCA+TX if channel busy)."""
        while self._slot != target:
            _, effective = self._stages[self._stage_idx % len(self._stages)]
            if effective == target or self._stage_idx >= len(self._stages) * 2:
                self._slot = target
                self._slot_start = time.monotonic()
                return
            self._stage_idx += 1

    # -- CCA ---------------------------------------------------------

    def cca(self, power_db: float) -> CCAReport:
        self._cca_power_window.append(power_db)
        free = power_db < self.cfg.cca_threshold_db

        if free:
            self._cca_ok += 1
        else:
            self._cca_fail += 1
            delay = self._backoff.next()
            if delay is not None:
                self._backoffs += 1
                time.sleep(delay)
            if self._backoff.exhausted:
                self._hopper.blacklist(self._hopper.current)
                self._hopper.force_hop()

        return CCAReport(
            channel_free=free,
            power_db=power_db,
            freq_hz=self._hopper.current,
            timestamp_s=time.monotonic(),
            retry_count=self._backoff.retries,
        )

    # Backward-compat alias
    perform_cca = cca

    def measure_power(self, iq: np.ndarray) -> float:
        if len(iq) == 0:
            return -100.0
        p = np.mean(np.abs(iq) ** 2)
        return float(10.0 * math.log10(p + 1e-20))

    # Backward-compat alias
    measure_channel_power = measure_power

    # -- channel feedback --------------------------------------------

    def record_channel_quality(self, freq: float, ok: int, total: int):
        self._hopper.quality.record(freq, ok, total)

    def log_frame(self, sf: SuperframeStats):
        self._frame_stats.append(sf)
        if len(self._frame_stats) > 256:
            self._frame_stats = self._frame_stats[-256:]

    def summary(self) -> str:
        s = self.stats
        tx_duty = 0
        rx_duty = 0
        if self._frame_id > 0:
            tx_duty = self._tx_frames * self.cfg.tx_duration_s / (
                self._frame_id * (self.cfg.tx_duration_s + self.cfg.rx_duration_s + self.cfg.guard_duration_s * 3)
            )
            rx_duty = self._rx_frames * self.cfg.rx_duration_s / (
                self._frame_id * (self.cfg.tx_duration_s + self.cfg.rx_duration_s + self.cfg.guard_duration_s * 3)
            )
        return (
            f"[MAC] frame={s['frame']} freq={self.frequency/1e6:.1f}MHz "
            f"TX={tx_duty:.1%} RX={rx_duty:.1%} "
            f"CCA_ok={s['cca_ok']} CCA_fail={s['cca_fail']} "
            f"hops={s['hops']} backoffs={s['backoffs']} "
            f"avail={s['channels_available']}/{len(self.cfg.hop_channels_hz)}"
        )


def make_contest_mac(team_id: int = 0, cca: bool = True) -> TDDController:
    channels = [2.405e9 + i * 5e6 for i in range(16)]
    np.random.seed(42 + team_id * 100)
    np.random.shuffle(channels)

    return TDDController(TDDConfig(
        cca_mode=CCAMode.ENERGY_DETECT if cca else CCAMode.OFF,
        hop_channels_hz=channels,
        tx_duration_s=0.070,
        rx_duration_s=0.040,
        guard_duration_s=0.005,
    ))


def make_aggressive_mac(team_id: int = 0) -> TDDController:
    """No CCA, more TX time — for fountain-code aggressive transmission."""
    return make_contest_mac(team_id, cca=False)

def create_competition_tdd_config(team_id: int = 0) -> TDDConfig:
    """Backward-compat: returns TDDConfig for the contest scenario."""
    channels = [2.405e9 + i * 5e6 for i in range(16)]
    np.random.seed(42 + team_id * 100)
    np.random.shuffle(channels)
    return TDDConfig(
        hop_channels_hz=channels,
        cca_mode=CCAMode.ENERGY_DETECT,
    )
