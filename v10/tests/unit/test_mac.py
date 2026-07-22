"""Tests for TDD MAC layer — updated for v2 MAC API."""

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
        assert config.tx_duration_s == 0.070
        assert config.rx_duration_s == 0.040
        assert config.guard_duration_s == 0.005
        assert len(config.hop_channels_hz) == 16
        assert config.cca_threshold_db == -65.0

    def test_validate_slots_fit(self):
        config = TDDConfig()
        issues = config.validate()
        assert issues == []

    def test_validate_overflow(self):
        config = TDDConfig(tx_duration_s=0.300, rx_duration_s=0.300)
        issues = config.validate()
        assert len(issues) == 1

    def test_create_competition_config(self):
        config = create_competition_tdd_config(team_id=5)
        assert len(config.hop_channels_hz) == 16
        assert config.cca_threshold_db == -65.0


class TestFrequencyHopper:
    def test_hopper_basic(self):
        channels = [2.4e9, 2.41e9, 2.42e9, 2.43e9]
        hopper = FrequencyHopper(channels)
        assert hopper.current == 2.4e9
        hopper.next()
        hopper.next()
        assert isinstance(hopper.current, float)

    def test_blacklist(self):
        channels = [2.4e9, 2.41e9, 2.42e9]
        hopper = FrequencyHopper(channels, blacklist_s=60.0)
        hopper.blacklist(2.41e9)
        assert hopper.num_available == 2  # one channel blacklisted

    def test_available_count(self):
        channels = [1e9, 2e9, 3e9]
        hopper = FrequencyHopper(channels)
        assert hopper.num_available == 3


class TestTDDController:
    def test_initial_state(self):
        tdd = TDDController(TDDConfig())
        assert tdd.slot == SlotType.IDLE

    def test_superframe_start(self):
        tdd = TDDController(TDDConfig())
        tdd.start_superframe()
        assert tdd.slot == SlotType.CCA

    def test_advance_slot_sequence(self):
        tdd = TDDController(TDDConfig())
        tdd.start_superframe()
        observed = []
        for _ in range(20):
            observed.append(tdd.slot)
            tdd.advance()
        assert SlotType.CCA in observed
        assert SlotType.TX in observed
        assert SlotType.RX in observed

    def test_cca_clear(self):
        tdd = TDDController(TDDConfig(cca_threshold_db=-50.0))
        report = tdd.cca(-80.0)
        assert report.channel_free is True
        assert report.power_db == -80.0

    def test_cca_busy(self):
        tdd = TDDController(TDDConfig(cca_threshold_db=-50.0))
        report = tdd.cca(-20.0)
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
        tdd.start_superframe()
        # Simulate repeated CCA failures
        for _ in range(8):
            tdd.cca(-20.0)

    def test_stats(self):
        tdd = TDDController(TDDConfig())
        tdd.start_superframe()
        for _ in range(10):
            tdd.cca(-80.0)
            tdd.advance()
        stats = tdd.stats
        assert stats["tx_frames"] >= 0
        assert stats["rx_frames"] >= 0

    def test_backward_compat(self):
        assert TDDController.start_superframe is TDDController.start_frame
        assert TDDController.advance_slot is TDDController.advance
        assert TDDController.perform_cca is TDDController.cca
        assert TDDController.measure_channel_power is TDDController.measure_power
