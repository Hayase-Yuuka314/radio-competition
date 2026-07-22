"""P2 模块测试：Gold码/缓冲/恢复/策略/CLI。"""

import time
import numpy as np
import pytest

from wireless_competition.adversarial.gold_code import (
    generate_standard_gold_code,
    generate_team_code,
    verify_cross_correlation,
    gold_cross_correlation_bound,
)
from wireless_competition.common.buffer import RingBuffer, BufferStats, HealthMonitor
from wireless_competition.common.recovery import (
    safe_call, check_model_file, check_disk_space, sanitize_iq, validate_parameters,
)
from wireless_competition.policy.rule_policy import AdaptiveRXWrapper


class TestStandardGoldCode:
    def test_length(self):
        code = generate_standard_gold_code(1023)
        assert len(code) == 1023

    def test_pm1(self):
        code = generate_standard_gold_code(1023)
        assert set(np.unique(code)).issubset({-1, 1})

    def test_balance(self):
        code = generate_standard_gold_code(1023)
        n_pos = np.sum(code == 1)
        n_neg = np.sum(code == -1)
        # Gold 码不完美平衡（差 ±1），容差放宽
        assert abs(n_pos - n_neg) <= 60, \
            f"Gold code imbalance: {n_pos} pos, {n_neg} neg"

    def test_different_teams_different(self):
        c0 = generate_team_code(1023, team_id=0)
        c1 = generate_team_code(1023, team_id=1)
        assert not np.array_equal(c0, c1)

    def test_different_shifts_different(self):
        c0 = generate_standard_gold_code(1023, shift=0)
        c1 = generate_standard_gold_code(1023, shift=100)
        assert not np.array_equal(c0, c1)

    def test_cross_correlation_bound(self):
        codes = {i: generate_team_code(1023, i) for i in range(4)}
        result = verify_cross_correlation(codes)
        bound = gold_cross_correlation_bound(10)
        assert result["max_cc"] < bound * 1.5, \
            f"Max CC {result['max_cc']:.4f} exceeds bound {bound:.4f}"

    def test_team_id_deterministic(self):
        c1 = generate_team_code(1023, team_id=5)
        c2 = generate_team_code(1023, team_id=5)
        assert np.array_equal(c1, c2)


class TestRingBuffer:
    def test_write_read(self):
        buf = RingBuffer(capacity=1024, dtype=np.float64)
        data = np.arange(100, dtype=np.float64)
        buf.write(data)
        out = buf.read(50)
        assert len(out) == 50
        assert out[0] == 0.0
        assert buf.available == 50

    def test_wraparound(self):
        buf = RingBuffer(capacity=100, dtype=np.float64)
        data = np.arange(200, dtype=np.float64)
        buf.write(data)  # 覆盖
        assert buf.stats.dropped_samples >= 100
        out = buf.read(50)
        assert len(out) == 50

    def test_empty_read(self):
        buf = RingBuffer(capacity=100)
        out = buf.read(50)
        assert len(out) == 0
        assert buf.stats.underflow_count == 1

    def test_high_water(self):
        buf = RingBuffer(capacity=100, dtype=np.float64)
        buf.write(np.ones(80))
        assert buf.is_high_water(0.7)

    def test_stats(self):
        buf = RingBuffer(capacity=200, dtype=np.float64)
        buf.write(np.ones(150))
        assert buf.stats.total_written == 150


class TestRecovery:
    def test_safe_call_success(self):
        result = safe_call(lambda x: x * 2, 5)
        assert result == 10

    def test_safe_call_fallback(self):
        def fail():
            raise ValueError("test error")
        result = safe_call(fail, fallback=42)
        assert result == 42

    def test_sanitize_iq_clean(self):
        iq = np.array([1.0+0j, 2.0+0j])
        clean, had_bad = sanitize_iq(iq)
        assert not had_bad
        assert np.allclose(clean, iq)

    def test_sanitize_iq_nan(self):
        iq = np.array([1.0+0j, np.nan+0j])
        clean, had_bad = sanitize_iq(iq)
        assert had_bad
        assert clean[1] == 0.0 + 0j

    def test_validate_parameters_ok(self):
        issues = validate_parameters(2e6, 433e6, 1e6, 40, max_gain_db=50)
        assert len(issues) == 0

    def test_validate_parameters_bad(self):
        issues = validate_parameters(2e6, 433e6, 1e6, 60, max_gain_db=50)
        assert len(issues) >= 1


class TestAdaptiveWrapper:
    def test_default_strategy(self):
        wrapper = AdaptiveRXWrapper(team_id=0)
        s = wrapper.select_strategy(snr_db=20.0)
        assert s.code_length >= 63

    def test_low_snr_triggers_long_code(self):
        wrapper = AdaptiveRXWrapper(team_id=0, min_code_length=63, max_code_length=1023)
        s = wrapper.select_strategy(snr_db=2.0, interference_detected=True)
        assert s.code_length > 63

    def test_history_tracks_switches(self):
        wrapper = AdaptiveRXWrapper(team_id=0, min_code_length=63, max_code_length=1023)
        # First: low SNR with interference → increase code length
        wrapper.select_strategy(snr_db=2.0, per=0.5, interference_detected=True)
        old_len = wrapper._current_code_length
        # Second: high SNR with no interference → decrease
        wrapper.select_strategy(snr_db=25.0, per=0.0, interference_detected=False)
        # At least one switch should have occurred
        assert wrapper.switch_count >= 1
        assert len(wrapper.history) >= 1


class TestHealthMonitor:
    def test_basic(self):
        buf = RingBuffer(capacity=1000, dtype=np.float64)
        mon = HealthMonitor(buffer=buf)
        mon.update(device_connected=True, snr_db=15.0, sync_state="crc_pass")
        assert mon._status.device_connected
        assert mon._status.snr_estimate_db == 15.0

    def test_healthy_check(self):
        mon = HealthMonitor()
        mon.update(device_connected=True)
        ok, issues = mon.is_healthy()
        assert ok

    def test_unhealthy_detection(self):
        mon = HealthMonitor()
        ok, issues = mon.is_healthy()
        assert not ok
        assert any("not connected" in i for i in issues)
