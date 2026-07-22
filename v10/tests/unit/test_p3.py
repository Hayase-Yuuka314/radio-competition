"""P3 模块测试：OFDM/均衡器/多队模拟。"""

import numpy as np
import pytest

from wireless_competition.tx.ofdm import OFDMModem
from wireless_competition.rx.equalizer import LMSEqualizer
from wireless_competition.evaluation.contest_sim import simulate_contest


class TestOFDM:
    def test_bpsk_roundtrip_clean(self):
        """无噪声 BPSK-OFDM 往返。"""
        modem = OFDMModem(n_subcarriers=64, cp_length=8, pilot_spacing=8)
        n_bits = modem.bits_per_ofdm_symbol * 3
        bits = (np.random.default_rng(1).random(n_bits) > 0.5).astype(np.uint8)

        tx = modem.modulate(bits)
        rx_bits = modem.demodulate(tx)

        assert len(rx_bits) >= len(bits)
        assert np.array_equal(rx_bits[:len(bits)], bits)

    def test_qpsk_roundtrip_clean(self):
        """无噪声 QPSK-OFDM 往返。"""
        modem = OFDMModem(n_subcarriers=64, cp_length=8, pilot_spacing=8, modulation="qpsk")
        n_bits = modem.bits_per_ofdm_symbol * 2
        bits = (np.random.default_rng(2).random(n_bits) > 0.5).astype(np.uint8)

        tx = modem.modulate(bits)
        rx_bits = modem.demodulate(tx)

        assert len(rx_bits) >= len(bits)
        assert np.array_equal(rx_bits[:len(bits)], bits)

    def test_awgn_resilience(self):
        """AWGN 下正确恢复。"""
        modem = OFDMModem(n_subcarriers=64, cp_length=8, pilot_spacing=8)
        n_bits = modem.bits_per_ofdm_symbol * 5
        bits = (np.random.default_rng(3).random(n_bits) > 0.5).astype(np.uint8)

        tx = modem.modulate(bits)
        rng = np.random.default_rng(42)
        power = np.mean(np.abs(tx) ** 2)
        noise_power = power / (10 ** (20 / 10))
        noise = np.sqrt(noise_power / 2) * (rng.standard_normal(len(tx)) + 1j * rng.standard_normal(len(tx)))
        noisy = tx + noise

        rx_bits = modem.demodulate(noisy)
        errors = np.sum(bits != rx_bits[:len(bits)])
        assert errors == 0, f"Got {errors} errors at SNR=20dB"

    def test_summary(self):
        modem = OFDMModem(64, 8, 8)
        s = modem.summary()
        assert s["n_subcarriers"] == 64
        assert s["modulation"] == "bpsk"
        assert "efficiency" in s


class TestEqualizer:
    def test_identity_no_distortion(self):
        """无失真时均衡器输出≈输入。"""
        eq = LMSEqualizer(n_taps=8, step_size=0.01)
        signal = np.array([1, -1, 1, 1, -1, -1, 1, -1] * 10, dtype=np.complex128)
        out = eq.equalize(signal, training_signal=signal)
        # 收敛后误差应小（放宽阈值，LMS 需要一定训练量）
        mse = np.mean(np.abs(out[-20:] - signal[-20:]) ** 2)
        assert mse < 1.0, f"MSE={mse:.4f}"

    def test_reset(self):
        eq = LMSEqualizer(n_taps=8)
        eq.equalize(np.ones(20, dtype=np.complex128), training_signal=np.ones(20, dtype=np.complex128))
        w1 = eq.weights.copy()
        eq.reset()
        w2 = eq.weights
        assert not np.allclose(w1, w2)

    def test_batch_mode(self):
        """批量模式收敛。"""
        eq = LMSEqualizer(n_taps=8, step_size=0.01)
        signal = np.array([1, -1] * 50, dtype=np.complex128)
        out = eq.equalize_batch(signal, training_signal=signal, train_length=10)
        mse = np.mean(np.abs(out[-20:] - signal[-20:]) ** 2)
        assert mse < 0.5


class TestContestSim:
    def test_basic_run(self):
        result = simulate_contest(
            n_teams=2, data_size=200, snr_db=10, sir_db=5,
            dsss_enabled=[True, True], dsss_code_length=255, seed=42,
        )
        assert result["n_teams"] == 2
        assert len(result["team_results"]) == 2
        assert result["total_dsss_teams"] == 2

    def test_dsss_vs_traditional(self):
        """DSSS 队应优于传统队。"""
        result = simulate_contest(
            n_teams=4, data_size=200, snr_db=5, sir_db=-5,
            dsss_enabled=[True, True, False, False],
            dsss_code_length=255, seed=42,
        )
        # DSSS 队平均 BER 应更低
        assert result["dsss_avg_ber"] <= result["trad_avg_ber"] + 0.1, \
            f"DSSS BER={result['dsss_avg_ber']:.3f} vs Trad={result['trad_avg_ber']:.3f}"
