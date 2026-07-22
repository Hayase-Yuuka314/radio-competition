"""Competition DSSS pipeline with standard Gold code integration.

Combines:
- Standard Gold codes from dsss.py (guaranteed 3-valued cross-correlation)
- Fountain packets as payload (no-ACK file transfer)
- DSSS spreading/despreading with chip-level synchronization
- Multi-team CDMA support for the competition scenario

Key design decisions:
- Spreading factor 128 (21 dB processing gain)
- Standard 10-order Gold codes, shift per team_id
- Preamble uses a sync-friendly PN sequence for frame acquisition
- Each fountain packet is spread across multiple DSSS sub-frames
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Optional

import numpy as np

from ..adversarial.dsss import (
    SpreadingCodeManager,
    despread,
    generate_spreading_code,
    processing_gain_db,
    spread,
)
from ..fountain.raptorq import FountainPacket, PACKET_HEADER_SIZE


@dataclass
class DSSSConfig:
    """Competition DSSS configuration."""
    team_id: int = 0
    spreading_factor: int = 128
    chip_rate_hz: float = 2.0e6
    preamble_length: int = 256
    samples_per_symbol: int = 2
    guard_chips: int = 64

    @property
    def processing_gain_db(self) -> float:
        return processing_gain_db(self.spreading_factor)

    @property
    def symbol_rate_hz(self) -> float:
        return self.chip_rate_hz / self.spreading_factor


class ContestDSSSEncoder:
    """Encodes fountain packets into DSSS IQ waveforms for transmission.

    Frame structure per fountain packet (baseband IQ):
        [Guard chips] [Preamble chips] [Sync chips] [Fountain packet bytes]
    """

    def __init__(self, config: DSSSConfig):
        self.config = config
        self.spf = config.spreading_factor
        self.preamble_len = config.preamble_length
        self.guard = config.guard_chips

        rng = np.random.default_rng(42 + config.team_id * 100)
        self._preamble_code = 2 * (rng.integers(0, 2, self.preamble_len).astype(np.int8)) - 1

        self._sync_code = generate_spreading_code(self.spf, team_id=-1).astype(np.int8)

        self._data_code = generate_spreading_code(
            self.spf, team_id=config.team_id
        ).astype(np.int8)

        self._sample_counter = 0

    def encode_packet(self, packet: FountainPacket) -> np.ndarray:
        """Encode one fountain packet into DSSS IQ waveform.

        Returns:
            Complex IQ samples at chip rate.
        """
        raw_data = packet.serialize()
        raw_bits = np.unpackbits(np.frombuffer(raw_data, dtype=np.uint8))

        signal_parts = []

        if self.guard > 0:
            signal_parts.append(np.zeros(self.guard, dtype=np.complex64))

        preamble_chips = self._preamble_code[:self.preamble_len]
        signal_parts.append(preamble_chips.astype(np.complex64))

        sync_chips = self._sync_code.astype(np.complex64)
        signal_parts.append(sync_chips)

        for bit in raw_bits:
            symbol = 1.0 if bit == 0 else -1.0
            chips = self._data_code.astype(np.float64) * symbol
            signal_parts.append(chips.astype(np.complex64))

        signal_parts.append(np.zeros(self.guard, dtype=np.complex64))

        self._sample_counter += sum(len(p) for p in signal_parts)
        return np.concatenate(signal_parts).astype(np.complex64)

    def encode_batch(self, packets: list[FountainPacket],
                     inter_packet_gap_chips: int = 256) -> np.ndarray:
        """Encode multiple fountain packets with gap between them."""
        result = []
        for pkt in packets:
            result.append(self.encode_packet(pkt))
            if inter_packet_gap_chips > 0:
                result.append(np.zeros(inter_packet_gap_chips, dtype=np.complex64))
        if not result:
            return np.array([], dtype=np.complex64)
        return np.concatenate(result)


class ContestDSSSDecoder:
    """Decodes DSSS IQ stream into fountain packets.

    Uses preamble correlation for frame detection, then despreads
    to recover fountain packet bytes, verifying via fountain packet
    header format.
    """

    MAX_PACKET_BYTES = 1024

    def __init__(self, config: DSSSConfig):
        self.config = config
        self.spf = config.spreading_factor
        self.preamble_len = config.preamble_length
        self.guard = config.guard_chips

        self._data_code = generate_spreading_code(
            self.spf, team_id=config.team_id
        ).astype(np.int8)

        rng = np.random.default_rng(42 + config.team_id * 100)
        self._preamble_code = 2 * (rng.integers(0, 2, self.preamble_len).astype(np.int8)) - 1

        self._sync_code = generate_spreading_code(self.spf, team_id=-1).astype(np.int8)

    def decode_frame(self, chips: np.ndarray, preamble_pos: int,
                     max_bits: int = 8192) -> Optional[FountainPacket]:
        """Decode one DSSS frame starting at preamble detection position.

        auto-detects complex IQ vs real and applies CFO correction if needed.
        """
        is_complex = np.iscomplexobj(chips) or chips.dtype in (np.complex64, np.complex128)
        chip_arr = np.asarray(chips, dtype=np.complex128 if is_complex else np.float64)
        preamble_ref = np.asarray(self._preamble_code, dtype=np.float64)
        chip_rate = self.config.chip_rate_hz

        # CFO estimation from preamble (complex only)
        cfo_hz = 0.0
        if is_complex:
            pre_start = preamble_pos
            pre_len = self.preamble_len
            if pre_start + pre_len <= len(chip_arr):
                pre_seg = chip_arr[pre_start:pre_start + pre_len]
                half = pre_len // 2
                a = np.dot(pre_seg[:half], preamble_ref[:half])
                b = np.dot(pre_seg[half:2*half], preamble_ref[half:2*half])
                cfo_hz = np.angle(b * np.conj(a)) / (2.0 * np.pi * half / chip_rate)
                if not np.isfinite(cfo_hz):
                    cfo_hz = 0.0

        # Sync word check
        pos = preamble_pos + self.preamble_len
        sync_len = len(self._sync_code)
        if pos + sync_len > len(chip_arr):
            return None

        sync_ref = np.asarray(self._sync_code, dtype=np.float64)
        sync_seg = chip_arr[pos:pos + sync_len]
        if is_complex and abs(cfo_hz) > 10.0:
            t = np.arange(sync_len, dtype=np.float64) / chip_rate
            sync_seg = sync_seg * np.exp(-1j * 2.0 * np.pi * cfo_hz * t)

        sync_corr = np.abs(np.dot(sync_seg, sync_ref)) if is_complex else abs(np.dot(sync_seg, sync_ref))
        if sync_corr < 0.5 * sync_len:
            return None

        pos += sync_len

        # Phase 1: read header bits (with CFO correction)
        header_bits_needed = PACKET_HEADER_SIZE * 8
        if pos + header_bits_needed * self.spf > len(chip_arr):
            return None

        data_ref = np.asarray(self._data_code, dtype=np.float64)
        header_bits = []
        for i in range(header_bits_needed):
            chip_seg = chip_arr[pos:pos + self.spf]
            if abs(cfo_hz) > 10.0:
                t = np.arange(self.spf, dtype=np.float64) / chip_rate
                chip_seg = chip_seg * np.exp(-1j * 2.0 * np.pi * cfo_hz * (t + (pos - preamble_pos - self.preamble_len - sync_len) / chip_rate))
            soft = np.dot(chip_seg.real, data_ref)
            header_bits.append(0 if soft > 0 else 1)
            pos += self.spf

        header_bytes = np.packbits(np.array(header_bits, dtype=np.uint8))
        try:
            pkt = FountainPacket.deserialize(bytes(header_bytes))
        except Exception:
            return None

        if not (pkt.k > 0 and pkt.total_size > 0):
            return None

        # Phase 2: compute payload size and check if enough chips remain
        payload_bytes = pkt.block_size
        payload_bits_needed = payload_bytes * 8

        # Verify enough chip stream remains for full payload
        remaining_chips = len(chip_arr) - pos
        chips_needed = payload_bits_needed * self.spf
        if remaining_chips < chips_needed:
            return None

        payload_bits = []
        for i in range(payload_bits_needed):
            chip_seg = chip_arr[pos:pos + self.spf]
            if abs(cfo_hz) > 10.0:
                total_offset = pos - preamble_pos - self.preamble_len - sync_len - header_bits_needed * self.spf
                t = np.arange(self.spf, dtype=np.float64) / chip_rate
                chip_seg = chip_seg * np.exp(-1j * 2.0 * np.pi * cfo_hz * (t + total_offset / chip_rate))
            soft = np.dot(chip_seg.real, data_ref)
            payload_bits.append(0 if soft > 0 else 1)
            pos += self.spf

        payload_arr = np.array(payload_bits, dtype=np.uint8)
        payload_arr = payload_arr[:payload_bytes * 8]
        if len(payload_arr) < payload_bytes * 8:
            pad = np.zeros(payload_bytes * 8 - len(payload_arr), dtype=np.uint8)
            payload_arr = np.concatenate([payload_arr, pad])

        all_bits = np.concatenate([np.array(header_bits, dtype=np.uint8), payload_arr])
        all_bytes = np.packbits(all_bits)

        try:
            pkt = FountainPacket.deserialize(bytes(all_bytes))
            if pkt.k > 0 and pkt.total_size > 0:
                return pkt
        except Exception:
            pass

        return None

    def process_stream(self, chips: np.ndarray) -> list[FountainPacket]:
        """Process continuous DSSS chip stream, extracting all fountain packets.

        Accepts both real(float64) and complex(complex128) IQ samples.
        Complex path enables CFO correction for real hardware.
        """
        if len(chips) < self.preamble_len:
            return []

        is_complex = np.iscomplexobj(chips) or chips.dtype in (np.complex64, np.complex128)
        chip_arr = np.asarray(chips, dtype=np.complex128 if is_complex else np.float64)
        preamble_ref = np.asarray(self._preamble_code, dtype=np.float64)

        corr = np.correlate(chip_arr, preamble_ref, mode="valid")
        corr_abs = np.abs(corr) if is_complex else np.abs(corr)
        threshold_val = 0.5 * self.preamble_len

        candidate_indices = np.where(corr_abs > threshold_val)[0]

        packets = []
        decoded_positions = set()

        for idx in candidate_indices:
            idx = int(idx)
            if any(abs(idx - dp) < self.preamble_len for dp in decoded_positions):
                continue

            pkt = self.decode_frame(chips, idx)
            if pkt is not None:
                packets.append(pkt)
                decoded_positions.add(idx)

        return packets


def create_contest_dsss(team_id: int, spreading_factor: int = 128) -> tuple[
    ContestDSSSEncoder, ContestDSSSDecoder
]:
    """Create matched Encoder/Decoder pair for a contest team."""
    config = DSSSConfig(
        team_id=team_id,
        spreading_factor=spreading_factor,
    )
    return ContestDSSSEncoder(config), ContestDSSSDecoder(config)
