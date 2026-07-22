"""单元测试：file_protocol 模块。

覆盖分块、帧头、CRC 和重组。
"""

import numpy as np
import pytest

from wireless_competition.common.types import FrameMetadata, ProfileID
from wireless_competition.file_protocol.chunker import (
    chunk_file,
    chunk_file_with_metadata,
    reassemble_file,
)
from wireless_competition.file_protocol.frame_header import (
    HEADER_LENGTH_BYTES,
    decode_header,
    encode_header,
    validate_header,
)
from wireless_competition.file_protocol.integrity import (
    append_crc32,
    check_crc32,
    crc32,
    crc32_finalize,
)
from wireless_competition.file_protocol.assembler import FileAssembler


# ── Chunker ─────────────────────────────────────────────────

class TestChunker:
    def test_chunk_exact(self):
        data = b"a" * 256
        blocks = chunk_file(data, block_size=64)
        assert len(blocks) == 4
        assert all(len(b) == 64 for b in blocks)

    def test_chunk_remainder(self):
        data = b"a" * 100
        blocks = chunk_file(data, block_size=64)
        assert len(blocks) == 2
        assert len(blocks[0]) == 64
        assert len(blocks[1]) == 36

    def test_chunk_empty(self):
        blocks = chunk_file(b"", block_size=64)
        assert len(blocks) == 0

    def test_chunk_with_metadata(self):
        data = b"x" * 128
        chunks = chunk_file_with_metadata(data, file_id=5, block_size=64)
        assert len(chunks) == 2
        fid, seq, total, payload = chunks[0]
        assert fid == 5
        assert seq == 0
        assert total == 2

    def test_reassemble(self):
        data = b"hello world! " * 20
        blocks = {0: data[:50], 1: data[50:100], 2: data[100:]}
        result = reassemble_file(blocks, total_blocks=3)
        assert result == data

    def test_reassemble_missing(self):
        with pytest.raises(ValueError, match="Missing"):
            reassemble_file({0: b"a"}, total_blocks=3)


# ── FrameHeader ──────────────────────────────────────────────

class TestFrameHeader:
    def test_roundtrip(self):
        meta = FrameMetadata(
            file_id=42,
            block_sequence=3,
            total_blocks=10,
            payload_length=256,
            profile_id=ProfileID.P1_ROBUST,
        )
        encoded = encode_header(meta)
        assert len(encoded) == HEADER_LENGTH_BYTES

        decoded, crc_ok = decode_header(encoded)
        assert crc_ok
        assert decoded.file_id == 42
        assert decoded.block_sequence == 3
        assert decoded.total_blocks == 10
        assert decoded.payload_length == 256

    def test_crc_corruption(self):
        meta = FrameMetadata(file_id=1, total_blocks=5, block_sequence=0)
        encoded = bytearray(encode_header(meta))
        encoded[3] ^= 0xFF  # 翻转一个字节
        decoded, crc_ok = decode_header(bytes(encoded))
        assert not crc_ok

    def test_validate_header(self):
        meta = FrameMetadata(protocol_version=1, total_blocks=10)
        issues = validate_header(meta)
        assert len(issues) == 0

    def test_validate_invalid(self):
        meta = FrameMetadata(protocol_version=0, total_blocks=0)
        issues = validate_header(meta)
        assert len(issues) > 0


# ── Integrity ────────────────────────────────────────────────

class TestIntegrity:
    def test_crc32_roundtrip(self):
        data = b"test data for CRC"
        with_crc = append_crc32(data)
        assert len(with_crc) == len(data) + 4

        payload, ok = check_crc32(with_crc)
        assert ok
        assert payload == data

    def test_crc32_failure(self):
        data = b"test"
        with_crc = append_crc32(data)
        corrupted = bytearray(with_crc)
        corrupted[1] ^= 0x01
        payload, ok = check_crc32(bytes(corrupted))
        assert not ok

    def test_crc32_incremental(self):
        data = b"hello world"
        # 分段计算
        crc = crc32(data[:5])
        crc = crc32(data[5:], initial=crc)
        full_crc = crc32(data)
        assert crc32_finalize(crc) == crc32_finalize(full_crc)


# ── Assembler ────────────────────────────────────────────────

class TestAssembler:
    def test_accept_and_complete(self):
        assembler = FileAssembler()
        for i in range(5):
            status = assembler.accept_raw(
                file_id=1, block_seq=i, total_blocks=5, payload=bytes([i]) * 10
            )
        assert assembler.is_complete(1)
        assert assembler.progress_fraction(1) == 1.0

    def test_dedup(self):
        assembler = FileAssembler()
        assembler.accept_raw(file_id=1, block_seq=0, total_blocks=2, payload=b"a")
        result = assembler.accept_raw(file_id=1, block_seq=0, total_blocks=2, payload=b"a")
        assert result is None  # 去重
        assert assembler.progress_fraction(1) == 0.5

    def test_get_missing(self):
        assembler = FileAssembler()
        assembler.accept_raw(file_id=1, block_seq=0, total_blocks=3, payload=b"a")
        assembler.accept_raw(file_id=1, block_seq=2, total_blocks=3, payload=b"c")
        missing = assembler.get_missing(1)
        assert missing == [1]
