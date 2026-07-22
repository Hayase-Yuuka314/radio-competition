"""对抗模块单元测试。"""

import numpy as np
import pytest

from wireless_competition.adversarial.dsss import (
    SpreadingCodeManager,
    spread,
    despread,
    generate_gold_code,
    generate_spreading_code,
    processing_gain_db,
)
from wireless_competition.adversarial.waveform import (
    AdversarialWaveform,
    FrameRandomizer,
)
from wireless_competition.adversarial.strategy import (
    AdversarialController,
    StrategyLevel,
)
from wireless_competition.adversarial.evaluation import (
    evaluate_dsss_performance,
    evaluate_multiteam_interference,
)


# ── DSSS 核心 ────────────────────────────────────────────────

class TestGoldCode:
    def test_length(self):
        for length in [63, 127, 255, 511, 1023]:
            code = generate_gold_code(length)
            assert len(code) == length

    def test_values_are_pm1(self):
        code = generate_gold_code(511)
        assert set(np.unique(code)).issubset({-1, 1})

    def test_different_seeds_different_codes(self):
        c1 = generate_gold_code(255, seed=1)
        c2 = generate_gold_code(255, seed=2)
        assert not np.array_equal(c1, c2)

    def test_same_seed_reproducible(self):
        c1 = generate_gold_code(255, seed=42)
        c2 = generate_gold_code(255, seed=42)
        assert np.array_equal(c1, c2)

    def test_balance(self):
        """Gold 码中 +1 和 -1 数量接近（标准 Gold 码三值相关允差 ~6.4%）。"""
        code = generate_gold_code(1023)
        n_pos = np.sum(code == 1)
        n_neg = np.sum(code == -1)
        # 标准 Gold 码 (n=10) 最大不平衡 = 65, 65/1023 ≈ 6.35%
        assert abs(n_pos - n_neg) <= len(code) * 0.07


class TestSpreading:
    def test_spread_despread_roundtrip(self):
        """扩频解扩应完全恢复。"""
        code = generate_gold_code(63)
        bits = np.array([0, 1, 0, 0, 1, 1, 0, 1] * 10, dtype=np.uint8)

        chips = spread(bits, code)
        assert len(chips) == len(bits) * len(code)

        recovered = despread(chips, code, output_bits=True)
        assert np.array_equal(bits[:len(recovered)], recovered[:len(bits)])

    def test_different_codes_dont_work(self):
        """不同码解扩应接近随机（BER 远离 0 也远离 1）。"""
        code1 = generate_gold_code(127, seed=1)
        code2 = generate_gold_code(127, seed=99)  # 远种子

        bits = (np.random.default_rng(0).random(1000) > 0.5).astype(np.uint8)
        chips = spread(bits, code1)

        # 用错误码解扩 → 应接近 50% 错误
        wrong = despread(chips, code2, output_bits=True)
        errors = np.sum(bits[:len(wrong)] != wrong)
        ber = errors / len(wrong)
        # 应在 0.35-0.65 之间（接近随机）。如果 BER≈1.0 说明码负相关，也说明码不同
        assert 0.3 < ber < 0.7 or ber > 0.95, f"BER={ber:.4f}"

    def test_processing_gain_formula(self):
        pg = processing_gain_db(1023)
        assert 29 < pg < 31  # ~30.1 dB

    def test_awgn_resilience(self):
        """DSSS 在噪声下应有明显处理增益。"""
        code = generate_spreading_code(255, team_id=0)
        bits = np.array([0, 1] * 200, dtype=np.uint8)

        chips = spread(bits, code)
        rng = np.random.default_rng(99)

        # SNR = -5dB: 噪声功率是信号的 3 倍
        power = np.mean(chips ** 2)
        noise_power = power / (10 ** (-5 / 10))
        noise = np.sqrt(noise_power) * rng.standard_normal(len(chips))
        noisy = chips + noise

        recovered = despread(noisy, code, output_bits=True)
        errors = np.sum(bits[:len(recovered)] != recovered)
        ber = errors / len(recovered)
        # 码长 255 → 处理增益 ~24dB，-5dB SNR 等效于 19dB 的 BPSK → BER 应极低
        assert ber < 0.01, f"BER={ber:.4f} too high for DSSS at SNR=-5dB"


# ── 对抗波形 ─────────────────────────────────────────────────

class TestAdversarialWaveform:
    def test_modulate_demodulate(self):
        wave = AdversarialWaveform(team_id=0, code_length=127)
        bits = (np.random.default_rng(1).random(500) > 0.5).astype(np.uint8)

        chips = wave.modulate(bits)
        recovered = wave.demodulate(chips)
        assert np.array_equal(bits[:len(recovered)], recovered[:len(bits)])

    def test_soft_demodulate(self):
        wave = AdversarialWaveform(team_id=0, code_length=127)
        bits = np.array([0, 1, 0, 1], dtype=np.uint8)
        chips = wave.modulate(bits, scramble=False)  # 不扰乱
        soft = wave.soft_demodulate(chips)
        # bit 0 → 正相关 (0映射为+1, chips=code, dot(code,code)=N>0)
        # bit 1 → 负相关
        assert soft[0] > 0
        assert soft[1] < 0

    def test_rival_signal_orthogonal(self):
        """两个队伍码的互相关应很低。"""
        wave = AdversarialWaveform(team_id=0, code_length=1023)
        props = wave.code_properties()
        for team, cc in props["cross_correlation_with_rivals"].items():
            assert cc < 0.1, f"{team} cross-correlation {cc:.4f} too high"

    def test_different_teams_different(self):
        w1 = AdversarialWaveform(team_id=0)
        w2 = AdversarialWaveform(team_id=1)
        # 同一组比特
        bits = np.zeros(100, dtype=np.uint8)
        chips1 = w1.modulate(bits)
        chips2 = w2.modulate(bits)
        # 码片序列应不同
        assert not np.array_equal(chips1[:100], chips2[:100])


# ── 帧随机化 ─────────────────────────────────────────────────

class TestFrameRandomizer:
    def test_reproducible(self):
        r1 = FrameRandomizer(seed=42)
        r2 = FrameRandomizer(seed=42)
        assert r1.randomize_preamble_length() == r2.randomize_preamble_length()
        assert r1.randomize_guard_length() == r2.randomize_guard_length()

    def test_in_range(self):
        r = FrameRandomizer(seed=1)
        for _ in range(100):
            pl = r.randomize_preamble_length(64, 16)
            assert 48 <= pl <= 80
            gl = r.randomize_guard_length(16, 8)
            assert 4 <= gl <= 24


# ── 策略控制器 ───────────────────────────────────────────────

class TestAdversarialController:
    def test_default_defensive(self):
        ctrl = AdversarialController(team_id=0)
        s = ctrl.select_strategy(snr_estimate_db=20.0)
        assert s.level == StrategyLevel.DEFENSIVE

    def test_low_snr_triggers_long_code(self):
        ctrl = AdversarialController(team_id=0, min_code_length=63)
        s = ctrl.select_strategy(snr_estimate_db=2.0, interference_detected=True)
        assert s.level == StrategyLevel.ADAPTIVE_LENGTH
        assert s.code_length > 63

    def test_high_snr_reduces_code(self):
        ctrl = AdversarialController(team_id=0, min_code_length=63)
        # 先设一个长码
        ctrl.select_strategy(snr_estimate_db=2.0, interference_detected=True)
        # 再在高 SNR 下缩短
        s = ctrl.select_strategy(snr_estimate_db=20.0)
        assert s.code_length <= ctrl._strategy_history[0].code_length

    def test_rival_detection_triggers_spectrum_fill(self):
        ctrl = AdversarialController(team_id=0)
        s = ctrl.select_strategy(
            snr_estimate_db=10.0,
            rival_count=2,
            goodput_bps=100.0,
            target_goodput_bps=1000.0,
        )
        assert s.level == StrategyLevel.SPECTRUM_FILL


# ── 评估 ────────────────────────────────────────────────────

class TestEvaluation:
    def test_evaluate_basic(self):
        result = evaluate_dsss_performance(
            n_bits=2000,
            code_length=127,
            snr_db_range=[-10, -5, 0, 10],
            seed=42,
        )
        assert len(result["snr_db"]) == 4
        # 在处理增益范围内，己方 BER 应明显低于对手
        # 在 SNR=-5dB 时：己方等效 SNR ~16dB (127→21dB增益)，对手仍接近随机
        assert result["our_ber"][1] < result["rival_ber"][1] or \
               result["our_ber"][2] < result["rival_ber"][2], \
            f"our={result['our_ber']} vs rival={result['rival_ber']}"

    def test_multiteam(self):
        result = evaluate_multiteam_interference(
            n_bits=2000,
            code_length=255,
            snr_db=5.0,
            sir_db=-10.0,  # 每个对手比我们强 10dB
            rival_team_ids=[1, 2],
            seed=42,
        )
        # 即使 2 个对手各强 10dB，DSSS 处理增益 24dB 仍能覆盖
        assert result["our_ber"] < 0.05, \
            f"DSSS should handle multiteam, got BER={result['our_ber']:.4f}"
