"""集成测试：核心 DSP 链路（符号级）。

测试 bytes → bits → modulate → AWGN → demodulate → bits → bytes
不依赖脉冲成形和帧结构。
"""

import numpy as np
import pytest

from wireless_competition.common.types import FECType, ModulationType
from wireless_competition.tx.modulation import (
    bits_to_bytes,
    bpsk_demodulate_hard,
    bpsk_modulate,
    bytes_to_bits,
    qpsk_demodulate_hard,
    qpsk_modulate,
)
from wireless_competition.tx.fec import encode, decode_hard
from wireless_competition.channel.awgn import add_awgn


def _random_data(size: int, seed: int = 42) -> bytes:
    return np.random.default_rng(seed).bytes(size)


class TestBPSKModemChain:
    """BPSK 调制解调链路。"""

    def test_ideal_no_noise(self):
        """无噪声：字节完美恢复。"""
        data = _random_data(100, 1)
        bits = bytes_to_bits(data)
        symbols = bpsk_modulate(bits)
        recovered_bits = bpsk_demodulate_hard(symbols)
        recovered = bits_to_bytes(recovered_bits[:len(bits)])
        assert recovered == data

    def test_awgn_high_snr(self):
        """高 SNR：BER ≈ 0。"""
        data = _random_data(100, 2)
        bits = bytes_to_bits(data)
        symbols = bpsk_modulate(bits)
        noisy = add_awgn(symbols, snr_db=20.0, rng=np.random.default_rng(42))
        recovered_bits = bpsk_demodulate_hard(noisy)
        recovered = bits_to_bytes(recovered_bits[:len(bits)])
        assert recovered == data

    def test_awgn_medium_snr(self):
        """中 SNR：大多数比特正确。"""
        data = _random_data(100, 3)
        bits = bytes_to_bits(data)
        symbols = bpsk_modulate(bits)
        noisy = add_awgn(symbols, snr_db=6.0, rng=np.random.default_rng(43))
        recovered_bits = bpsk_demodulate_hard(noisy)
        errors = int(np.sum(bits != recovered_bits[:len(bits)]))
        ber = errors / len(bits)
        # BPSK at 6dB SNR: BER ~ 2e-3
        assert ber < 0.1, f"BER={ber:.4f} too high"


class TestQPSKModemChain:
    """QPSK 调制解调链路。"""

    def test_ideal_no_noise(self):
        """无噪声：字节完美恢复。"""
        data = _random_data(100, 10)
        bits = bytes_to_bits(data)
        symbols = qpsk_modulate(bits)
        recovered_bits = qpsk_demodulate_hard(symbols)
        recovered = bits_to_bytes(recovered_bits[:len(bits)])
        assert recovered == data


class TestFECChain:
    """FEC 编码译码链路。"""

    def test_convolutional_ideal(self):
        """无噪声理想信道。"""
        data = _random_data(100, 20)
        bits = bytes_to_bits(data)
        encoded = encode(bits, FECType.CONVOLUTIONAL)
        decoded = decode_hard(encoded, FECType.CONVOLUTIONAL, len(bits))
        recovered = bits_to_bytes(decoded[:len(bits)])
        assert recovered == data

    def test_convolutional_awgn(self):
        """卷积码 + AWGN 对比无编码。"""
        data = _random_data(200, 21)
        bits = bytes_to_bits(data)

        # 无编码
        symbols_uncoded = bpsk_modulate(bits)
        noisy_uncoded = add_awgn(symbols_uncoded, snr_db=5.0,
                                  rng=np.random.default_rng(100))
        recovered_uncoded = bpsk_demodulate_hard(noisy_uncoded)
        errors_uncoded = int(np.sum(bits != recovered_uncoded[:len(bits)]))

        # 卷积编码
        encoded = encode(bits, FECType.CONVOLUTIONAL)
        symbols_coded = bpsk_modulate(encoded)
        noisy_coded = add_awgn(symbols_coded, snr_db=5.0,
                               rng=np.random.default_rng(100))
        # 软解调 + 硬译码
        llr = 2.0 * np.real(noisy_coded) / (10**(-5.0/10))  # approx sigma^2
        decoded = decode_hard((llr <= 0).astype(np.uint8), FECType.CONVOLUTIONAL, len(bits))
        errors_coded = int(np.sum(bits != decoded[:len(bits)]))

        # 编码不应更差
        assert errors_coded <= errors_uncoded + 10, \
            f"FEC errors={errors_coded} > uncoded={errors_uncoded}"
