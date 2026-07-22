"""Tests for fountain code (RaptorQ-like LT codes)."""

import hashlib
import os

import numpy as np
import pytest

from wireless_competition.fountain.raptorq import (
    FountainDecoder,
    FountainEncoder,
    FountainPacket,
    _derive_neighbors,
    _robust_soliton_degree,
    _xor_block,
    fountain_decode,
    fountain_encode_file,
)


class TestXorBlock:
    def test_xor_equal_length(self):
        assert _xor_block(b"\x00\x01", b"\x00\x01") == b"\x00\x00"
        assert _xor_block(b"\xff\xff", b"\xff\xff") == b"\x00\x00"
        assert _xor_block(b"\xaa\x55", b"\x55\xaa") == b"\xff\xff"

    def test_xor_unequal_length(self):
        assert _xor_block(b"\x01\x02\x03", b"\xff") == b"\xfe\x02\x03"
        assert _xor_block(b"\xff", b"\x01\x02\x03") == b"\xfe\x02\x03"


class TestRobustSoliton:
    def test_degree_in_range(self):
        rng = np.random.RandomState(42)
        for k in [10, 50, 100, 256]:
            for _ in range(100):
                d = _robust_soliton_degree(rng, k)
                assert 1 <= d <= k, f"Degree {d} out of [1, {k}]"

    def test_degree_distribution_shape(self):
        """Verify degree=1 has reasonable probability mass."""
        rng = np.random.RandomState(42)
        k = 50
        counts = {d: 0 for d in range(1, k + 1)}
        for _ in range(10000):
            d = _robust_soliton_degree(rng, k)
            counts[d] += 1
        p1 = counts[1] / 10000
        assert p1 > 0.01, f"P(degree=1) too low: {p1:.4f}"


class TestDeriveNeighbors:
    def test_systematic_packets_have_degree_one(self):
        k = 50
        for pid in range(k):
            neighbors = _derive_neighbors(pid, k, 0)
            assert len(neighbors) == 1, f"Systematic packet {pid} should have degree 1"

    def test_repair_packets_deterministic(self):
        k = 50
        n1 = _derive_neighbors(100, k, 0)
        n2 = _derive_neighbors(100, k, 0)
        assert n1 == n2


class TestFountainPacket:
    def test_serialize_deserialize(self):
        pkt = FountainPacket(
            packet_id=42, file_id=1, k=100, total_size=1024, block_size=256,
            payload=b"hello world",
        )
        data = pkt.serialize()
        pkt2 = FountainPacket.deserialize(data)
        assert pkt2.packet_id == 42
        assert pkt2.file_id == 1
        assert pkt2.k == 100
        assert pkt2.total_size == 1024
        assert pkt2.payload == b"hello world"

    def test_deserialize_short_raises(self):
        with pytest.raises(ValueError):
            FountainPacket.deserialize(b"\x00" * 4)


class TestFountainEncoder:
    def test_basic_properties(self):
        data = b"A" * 500
        encoder = FountainEncoder(data, block_size=100)
        assert encoder.source_blocks == 5
        assert encoder.total_size == 500
        assert encoder.k == 5

    def test_systematic_stream(self):
        data = b"A" * 200 + b"B" * 200
        encoder = FountainEncoder(data, block_size=128)
        pkts = []
        for i, pkt in enumerate(encoder.encode_systematic_stream()):
            pkts.append(pkt)
            if i >= 10:
                break

        assert len(pkts) >= 3
        assert pkts[0].packet_id == 0
        assert pkts[0].payload == data[:128]
        assert pkts[1].packet_id == 1
        assert pkts[1].payload == data[128:256]

    def test_iter_produces_packets(self):
        data = b"A" * 300
        encoder = FountainEncoder(data, block_size=128)
        pkts = [next(encoder) for _ in range(50)]
        assert len(pkts) == 50
        assert all(isinstance(p, FountainPacket) for p in pkts)


class TestFountainDecoder:
    def test_decode_ideal_no_loss(self):
        data = b"test data for fountain decode test" * 20
        encoder = FountainEncoder(data, block_size=64)

        pkts = []
        for pkt in encoder.encode_systematic_stream():
            pkts.append(pkt)
            if pkt.packet_id >= encoder.k - 1:
                break

        decoder = FountainDecoder()
        for pkt in pkts:
            decoder.add_packet(pkt)
        assert decoder.can_decode()
        result = decoder.decode()
        assert result is not None
        assert result[:len(data)] == data

    def test_decode_with_overhead(self):
        np.random.seed(42)
        data = b"fountain code stress test" * 50
        encoder = FountainEncoder(data, block_size=128, seed=7)

        decoder = FountainDecoder()
        total_sent = 0
        for pkt in encoder:
            if np.random.random() < 0.3:
                continue
            decoder.add_packet(pkt)
            total_sent += 1
            if decoder.can_decode():
                result = decoder.decode()
                if result is not None and result[:len(data)] == data:
                    break
            if total_sent > encoder.k * 3:
                break

        assert total_sent < encoder.k * 3
        assert result is not None
        assert result[:len(data)] == data

    def test_small_file(self):
        data = b"hi"
        encoder = FountainEncoder(data, block_size=256, seed=1)

        decoder = FountainDecoder()
        for pkt in encoder:
            decoder.add_packet(pkt)
            if decoder.can_decode():
                result = decoder.decode()
                if result is not None:
                    break

        assert result is not None
        assert result == data

    def test_medium_file(self):
        data = os.urandom(8192)
        encoder = FountainEncoder(data, block_size=512, seed=5)

        decoder = FountainDecoder()
        for pkt in encoder:
            decoder.add_packet(pkt)
            if decoder.can_decode() and decoder.num_collected >= encoder.k + 20:
                result = decoder.decode()
                if result is not None and result == data:
                    break

        assert result is not None
        assert result == data

    def test_reset(self):
        decoder = FountainDecoder()
        pkt = FountainPacket(packet_id=0, file_id=1, k=10, total_size=256, block_size=256,
                             payload=b"x" * 256)
        decoder.add_packet(pkt)
        assert decoder.num_collected == 1
        decoder.reset()
        assert decoder.num_collected == 0
        assert decoder.k is None

    def test_duplicate_packet_ignored(self):
        decoder = FountainDecoder()
        pkt = FountainPacket(packet_id=5, file_id=1, k=10, total_size=256, block_size=256,
                             payload=b"x" * 100)
        decoder.add_packet(pkt)
        decoder.add_packet(pkt)
        assert decoder.num_collected == 1


class TestFountainConvenience:
    def test_fountain_decode_helper(self):
        data = b"helper test data"
        encoder = FountainEncoder(data, block_size=32, seed=2)

        pkts = []
        for pkt in encoder:
            pkts.append(pkt)
            if len(pkts) >= encoder.k + 20:
                break

        result = fountain_decode(pkts)
        assert result is not None
        assert result[:len(data)] == data
