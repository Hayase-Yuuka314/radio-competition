"""单元测试：tx 模块。

覆盖调制、脉冲成形、FEC、交织和组帧。
"""

import numpy as np
import pytest

from wireless_competition.common.types import FECType, ModulationType, ProfileID
from wireless_competition.tx.modulation import (
    bits_to_bytes,
    bpsk_demodulate_hard,
    bpsk_modulate,
    bytes_to_bits,
    qpsk_demodulate_hard,
    qpsk_modulate,
)
from wireless_competition.tx.pulse_shaping import (
    downsample,
    matched_filter,
    pulse_shape,
    rrc_filter,
    upsample,
)
from wireless_competition.tx.fec import (
    convolutional_decode_hard,
    convolutional_encode,
    decode_hard,
    encode,
    repetition_decode_hard,
    repetition_encode,
)
from wireless_competition.tx.interleaver import (
    block_deinterleave,
    block_interleave,
)
from wireless_competition.tx.framing import (
    build_frame,
    make_guard,
    make_preamble,
    make_sync_word,
)


# ── Modulation ───────────────────────────────────────────────

class TestModulation:
    def test_bytes_bits_roundtrip(self):
        data = bytes(range(256))
        bits = bytes_to_bits(data)
        recovered = bits_to_bytes(bits)
        assert recovered == data

    def test_bytes_to_bits_length(self):
        bits = bytes_to_bits(b"\xff")
        assert len(bits) == 8
        assert np.all(bits == 1)

    def test_bpsk_modulate_0(self):
        sym = bpsk_modulate(np.array([0]))
        assert np.isclose(np.real(sym[0]), 1.0)

    def test_bpsk_modulate_1(self):
        sym = bpsk_modulate(np.array([1]))
        assert np.isclose(np.real(sym[0]), -1.0)

    def test_bpsk_demod_roundtrip(self):
        bits = np.array([0, 1, 0, 0, 1, 1, 0, 1], dtype=np.uint8)
        symbols = bpsk_modulate(bits)
        recovered = bpsk_demodulate_hard(symbols)
        assert np.array_equal(bits, recovered)

    def test_qpsk_modulate_shape(self):
        # 偶数长度
        bits = np.array([0, 0, 0, 1, 1, 1, 1, 0], dtype=np.uint8)
        symbols = qpsk_modulate(bits)
        assert len(symbols) == 4

    def test_qpsk_roundtrip(self):
        bits = np.tile(np.array([0, 0, 0, 1, 1, 1, 1, 0], dtype=np.uint8), 10)
        symbols = qpsk_modulate(bits)
        recovered = qpsk_demodulate_hard(symbols)
        assert np.array_equal(bits[:len(recovered)], recovered)

    def test_qpsk_odd_bits_raises(self):
        with pytest.raises(ValueError):
            qpsk_modulate(np.array([0, 0, 0]))


# ── Pulse Shaping ────────────────────────────────────────────

class TestPulseShaping:
    def test_rrc_energy(self):
        rrc = rrc_filter(samples_per_symbol=8, rolloff=0.35, span=6)
        energy = np.sum(np.abs(rrc) ** 2)
        assert np.isclose(energy, 1.0, atol=0.01)

    def test_upsample(self):
        sym = np.array([1+0j, 0+1j])
        up = upsample(sym, 4)
        assert len(up) == 8
        assert up[0] == 1+0j
        assert up[4] == 0+1j

    def test_pulse_shape(self):
        sym = bpsk_modulate(np.array([0, 1, 0, 1], dtype=np.uint8))
        shaped = pulse_shape(sym, samples_per_symbol=8)
        assert len(shaped) > len(sym) * 8  # 含滤波器延迟


# ── FEC ──────────────────────────────────────────────────────

class TestFEC:
    def test_no_fec(self):
        bits = np.array([0, 1, 0, 1], dtype=np.uint8)
        encoded = encode(bits, FECType.NONE)
        assert np.array_equal(encoded, bits)

    def test_repetition_roundtrip(self):
        bits = np.array([0, 1, 0, 1], dtype=np.uint8)
        encoded = repetition_encode(bits, repeat=3)
        decoded = repetition_decode_hard(encoded, repeat=3)
        assert np.array_equal(decoded, bits)

    def test_convolutional_roundtrip(self):
        bits = np.array(
            [0, 1, 0, 0, 1, 1, 0, 1] * 20, dtype=np.uint8
        )
        encoded = convolutional_encode(bits)
        decoded = convolutional_decode_hard(encoded)
        assert np.array_equal(decoded[:len(bits)], bits)

    def test_encode_decode_dispatch(self):
        bits = np.array([0, 1] * 50, dtype=np.uint8)
        for fec in [FECType.NONE, FECType.REPETITION, FECType.CONVOLUTIONAL]:
            encoded = encode(bits, fec)
            decoded = decode_hard(encoded, fec, original_bit_count=len(bits))
            assert len(decoded) > 0, f"FEC {fec} failed"


# ── Interleaver ──────────────────────────────────────────────

class TestInterleaver:
    def test_block_roundtrip(self):
        bits = np.arange(64, dtype=np.uint8) % 2
        inter = block_interleave(bits, 8)
        deinter = block_deinterleave(inter, 8)
        assert np.array_equal(bits[:len(deinter)], deinter[:len(bits)])

    def test_block_different(self):
        bits = np.arange(32, dtype=np.uint8) % 2
        inter = block_interleave(bits, 8)
        assert not np.array_equal(bits, inter)


# ── Framing ──────────────────────────────────────────────────

class TestFraming:
    def test_make_preamble(self):
        p = make_preamble(8, 64)
        assert len(p) == 64
        # Zadoff-Chu 恒幅
        assert np.allclose(np.abs(p), 1.0)

    def test_make_sync_word(self):
        sw = make_sync_word()
        assert len(sw) == 16

    def test_make_guard(self):
        g = make_guard(8, 16)
        assert len(g) == 16  # 16 符号
        assert np.all(g == 0)

    def test_build_frame(self):
        from wireless_competition.common.types import FrameMetadata

        meta = FrameMetadata(
            file_id=0,
            block_sequence=0,
            total_blocks=1,
            payload_length=32,
        )
        frame = build_frame(
            payload=b"hello world! " * 3,
            metadata=meta,
            modulation=ModulationType.BPSK,
            fec_type=FECType.NONE,
            samples_per_symbol=8,
        )
        assert len(frame) > 0
        assert frame.dtype == np.complex128
