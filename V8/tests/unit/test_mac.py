"""Tests for TDD MAC layer."""

import time

import numpy as np
import pytest

from wireless_competition.mac.tdd import (
    CCAReport,
    FrequencyHopper,
    SlotType,
    TDDConfig,
    TDDController,
    create_competition_tdd_config,
)


class TestTDDConfig:
    def test_default_config(self):
        config = TDDConfig()
        assert config.superframe_duration_s == 0.200
        assert config.cca_duration_s == 0.005
        assert config.tx_duration_s == 0.080
        assert config.rx_duration_s == 0.080
        assert config.guard_duration_s == 0.005
        assert len(config.hop_channels_hz) == 16
        assert config.cca_threshold_db == -70.0

    def test_validate_slots_fit(self):
        config = TDDConfig()
        issues = config.validate()
        assert issues == []

    def test_validate_overflow(self):
        config = TDDConfig(tx_duration_s=0.200, rx_duration_s=0.200,
                           cca_duration_s=0.200, guard_duration_s=0.200)
        issues = config.validate()
        assert len(issues) == 1

    def test_create_competition_config(self):
        config = create_competition_tdd_config(team_id=5)
        assert len(config.hop_channels_hz) == 16
        assert config.cca_threshold_db == -70.0


class TestFrequencyHopper:
    def test_sequential_hopping(self):
        channels = [2.4e9, 2.41e9, 2.42e9, 2.43e9]
        hopper = FrequencyHopper(channels, hop_interval=1)

        assert hopper.current == 2.4e9
        for expected in [2.41e9, 2.42e9, 2.43e9, 2.4e9, 2.41e9]:
            assert hopper.next() == expected

    def test_blacklist(self):
        channels = [2.4e9, 2.41e9, 2.42e9]
        hopper = FrequencyHopper(channels, hop_interval=1, blacklist_timeout_s=60.0)

        hopper.next()
        hopper.blacklist_current()
        assert 2.41e9 not in hopper.active_channels

    def test_active_channels(self):
        channels = [1e9, 2e9, 3e9]
        hopper = FrequencyHopper(channels)
        assert hopper.active_channels == channels


class TestTDDController:
    def test_initial_state(self):
        tdd = TDDController(TDDConfig())
        assert tdd.current_slot == SlotType.GUARD

    def test_superframe_start(self):
        tdd = TDDController(TDDConfig())
        tdd.start_superframe()
        assert tdd.current_slot == SlotType.CCA

    def test_advance_slot_sequence(self):
        tdd = TDDController(TDDConfig())
        tdd.start_superframe()

        observed = []
        for _ in range(30):
            observed.append(tdd.current_slot)
            tdd.advance_slot()

        assert SlotType.CCA in observed
        assert SlotType.TX in observed
        assert SlotType.RX in observed

    def test_cca_clear(self):
        tdd = TDDController(TDDConfig(cca_threshold_db=-50.0))

        report = tdd.perform_cca(-80.0)
        assert report.channel_free is True
        assert report.measured_power_db == -80.0

    def test_cca_busy(self):
        tdd = TDDController(TDDConfig(cca_threshold_db=-50.0))

        report = tdd.perform_cca(-20.0)
        assert report.channel_free is False

    def test_measure_channel_power(self):
        tdd = TDDController(TDDConfig())
        noise = (np.random.randn(4096) + 1j * np.random.randn(4096)) * 0.01
        noise = noise.astype(np.complex64)
        power = tdd.measure_channel_power(noise)
        assert power < -20.0

        signal = (np.random.randn(4096) + 1j * np.random.randn(4096)) * 0.5
        signal = signal.astype(np.complex64)
        power = tdd.measure_channel_power(signal)
        assert power > -20.0

    def test_backoff_does_not_crash(self):
        tdd = TDDController(TDDConfig())
        for _ in range(8):
            tdd.perform_cca(-20.0)
        tdd.backoff()

    def test_stats(self):
        tdd = TDDController(TDDConfig())
        tdd.start_superframe()

        for _ in range(10):
            tdd.perform_cca(-80.0)
            tdd.advance_slot()

        stats = tdd.stats
        assert stats["tx_slots"] >= 0
        assert stats["rx_slots"] >= 0
