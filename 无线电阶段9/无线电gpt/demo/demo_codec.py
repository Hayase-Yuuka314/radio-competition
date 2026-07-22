"""Standalone codec used by the two GNU Radio Companion demo flowgraphs.

The implementation deliberately mirrors the repository's tested building blocks:

* BPSK symbols and the same pseudo-Gold spreading-code generator used by
  ``wireless_competition.adversarial.dsss``;
* rate-1/2, K=7 convolutional FEC (0o171/0o133) and soft Viterbi decoding;
* the repository's block interleaver/deinterleaver;
* shared-key XOR whitening and CRC-32 validation.

The extra acquisition tone, sync word and periodic pilots make the otherwise
simulation-oriented DSSS chain usable with asynchronous PlutoSDR clocks.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import time
import zlib

import numpy as np


# Prefer the project's actual implementations.  The fallbacks below are kept so
# that copying the demo folder by itself still works in a RadioConda environment.
_REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
_SRC = _REPOSITORY_ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

try:
    from wireless_competition.adversarial.dsss import (  # type: ignore
        generate_spreading_code as _project_spreading_code,
    )
    from wireless_competition.tx.fec import (  # type: ignore
        convolutional_decode_soft as _project_conv_decode_soft,
        convolutional_encode as _project_conv_encode,
    )
    from wireless_competition.tx.interleaver import (  # type: ignore
        block_deinterleave as _project_deinterleave,
        block_interleave as _project_interleave,
    )

    PROJECT_BACKEND = True
except Exception:
    _project_spreading_code = None
    _project_conv_decode_soft = None
    _project_conv_encode = None
    _project_deinterleave = None
    _project_interleave = None
    PROJECT_BACKEND = False


MAGIC = b"DK"
VERSION = 1
MAX_PAYLOAD_BYTES = 16
FEC_TAIL_BITS = 6
INTERLEAVER_BLOCK = 18
DATA_BITS_PER_PILOT = 64
ACQUISITION_TONE_HZ = 62_500.0
ACQUISITION_SAMPLES = 2048
SYNC_CHIPS = 255
PILOT_CHIPS = 127


@dataclass(frozen=True)
class DemoConfig:
    """Parameters which must match at TX and RX."""

    sample_rate: int = 1_000_000
    samples_per_chip: int = 4
    code_length: int = 31
    team_id: int = 0
    shared_key: str = "demo-shared-key-2026"
    amplitude: float = 0.25
    gap_samples: int = 25_000
    sequence: int = 1

    def validate(self) -> None:
        if self.sample_rate < 520_834:
            raise ValueError("PlutoSDR sample_rate must be at least about 520834 S/s")
        if self.samples_per_chip < 2:
            raise ValueError("samples_per_chip must be >= 2")
        if self.code_length < 7:
            raise ValueError("code_length must be >= 7")
        if not self.shared_key:
            raise ValueError("shared_key must not be empty")
        if not (0.01 <= self.amplitude <= 0.8):
            raise ValueError("amplitude must be between 0.01 and 0.8")
        if self.gap_samples < 4096:
            raise ValueError("gap_samples must be >= 4096 for burst acquisition")

    @property
    def raw_packet_bytes(self) -> int:
        # magic(2) + version(1) + sequence(2) + length(1) + payload(16) + CRC32(4)
        return 2 + 1 + 2 + 1 + MAX_PAYLOAD_BYTES + 4

    @property
    def uncoded_bits(self) -> int:
        return self.raw_packet_bytes * 8 + FEC_TAIL_BITS

    @property
    def coded_bits(self) -> int:
        return self.uncoded_bits * 2

    @property
    def data_blocks(self) -> int:
        return math.ceil(self.coded_bits / DATA_BITS_PER_PILOT)

    @property
    def sync_samples(self) -> int:
        return SYNC_CHIPS * self.samples_per_chip

    @property
    def pilot_samples(self) -> int:
        return PILOT_CHIPS * self.samples_per_chip

    @property
    def active_samples(self) -> int:
        data_samples = self.coded_bits * self.code_length * self.samples_per_chip
        return (
            ACQUISITION_SAMPLES
            + self.sync_samples
            + self.data_blocks * self.pilot_samples
            + data_samples
        )

    @property
    def cycle_samples(self) -> int:
        return self.gap_samples + self.active_samples

    @property
    def processing_gain_db(self) -> float:
        return 10.0 * math.log10(self.code_length)


@dataclass
class DecodeResult:
    message: str
    payload_hex: str
    sequence: int
    crc_ok: bool
    sync_score: float
    minimum_pilot_score: float
    cfo_hz: float
    sample_start: int
    sample_end: int
    timestamp: str

    def to_dict(self) -> dict:
        return asdict(self)


def _gold_code(length: int, seed: int) -> np.ndarray:
    """Repository-compatible pseudo-Gold code (the same taps and seed rule)."""

    rng = np.random.default_rng(seed)
    reg1 = int(rng.integers(1, 2**10, dtype=np.int64))
    reg2 = int(rng.integers(1, 2**10, dtype=np.int64))
    code = np.zeros(int(length), dtype=np.int8)
    for index in range(int(length)):
        bit1 = ((reg1 >> 9) ^ (reg1 >> 5) ^ reg1) & 1
        reg1 = ((reg1 << 1) | bit1) & 0x3FF
        bit2 = ((reg2 >> 9) ^ (reg2 >> 7) ^ (reg2 >> 3) ^ reg2) & 1
        reg2 = ((reg2 << 1) | bit2) & 0x3FF
        code[index] = 1 if (bit1 ^ bit2) == 0 else -1
    return code


def spreading_code(config: DemoConfig) -> np.ndarray:
    if PROJECT_BACKEND:
        return np.asarray(
            _project_spreading_code(config.code_length, config.team_id), dtype=np.float64
        )
    return _gold_code(config.code_length, 42 + config.team_id * 100).astype(np.float64)


def _conv_encode_fallback(bits: np.ndarray) -> np.ndarray:
    bits = np.asarray(bits, dtype=np.uint8).ravel()
    encoded = np.zeros(len(bits) * 2, dtype=np.uint8)
    state = 0
    for index, value in enumerate(bits):
        bit = int(value)
        b5, b4, b3 = (state >> 5) & 1, (state >> 4) & 1, (state >> 3) & 1
        b1, b0 = (state >> 1) & 1, state & 1
        encoded[2 * index] = bit ^ b5 ^ b4 ^ b3 ^ b0
        encoded[2 * index + 1] = bit ^ b4 ^ b3 ^ b1 ^ b0
        state = ((state << 1) | bit) & 0x3F
    return encoded


def convolutional_encode(bits: np.ndarray) -> np.ndarray:
    if PROJECT_BACKEND:
        return np.asarray(_project_conv_encode(bits), dtype=np.uint8)
    return _conv_encode_fallback(bits)


def _build_trellis() -> tuple[np.ndarray, np.ndarray]:
    next_state = np.zeros((64, 2), dtype=np.int16)
    outputs = np.zeros((64, 2, 2), dtype=np.uint8)
    for state in range(64):
        for bit in (0, 1):
            b5, b4, b3 = (state >> 5) & 1, (state >> 4) & 1, (state >> 3) & 1
            b1, b0 = (state >> 1) & 1, state & 1
            outputs[state, bit, 0] = bit ^ b5 ^ b4 ^ b3 ^ b0
            outputs[state, bit, 1] = bit ^ b4 ^ b3 ^ b1 ^ b0
            next_state[state, bit] = ((state << 1) | bit) & 0x3F
    return next_state, outputs


_NEXT_STATE, _OUTPUTS = _build_trellis()


def _conv_decode_soft_fallback(llr: np.ndarray) -> np.ndarray:
    values = np.asarray(llr, dtype=np.float64).ravel()
    if len(values) % 2:
        raise ValueError("soft Viterbi input length must be even")
    steps = len(values) // 2
    metrics = np.full(64, np.inf)
    metrics[0] = 0.0
    previous = np.zeros((steps, 64), dtype=np.int16)
    previous_bit = np.zeros((steps, 64), dtype=np.uint8)
    for step in range(steps):
        pair = values[2 * step : 2 * step + 2]
        new_metrics = np.full(64, np.inf)
        for state in range(64):
            if not np.isfinite(metrics[state]):
                continue
            for bit in (0, 1):
                expected = _OUTPUTS[state, bit]
                cost = float(np.sum(-0.5 * (1.0 - 2.0 * expected) * pair))
                destination = int(_NEXT_STATE[state, bit])
                candidate = metrics[state] + cost
                if candidate < new_metrics[destination]:
                    new_metrics[destination] = candidate
                    previous[step, destination] = state
                    previous_bit[step, destination] = bit
        metrics = new_metrics
    # The encoder appends six zero tail bits, so state zero is the expected end.
    state = 0 if np.isfinite(metrics[0]) else int(np.argmin(metrics))
    decoded = np.zeros(steps, dtype=np.uint8)
    for step in range(steps - 1, -1, -1):
        decoded[step] = previous_bit[step, state]
        state = int(previous[step, state])
    return decoded


def convolutional_decode_soft(llr: np.ndarray) -> np.ndarray:
    if PROJECT_BACKEND:
        return np.asarray(_project_conv_decode_soft(llr), dtype=np.uint8)
    return _conv_decode_soft_fallback(llr)


def block_interleave(values: np.ndarray) -> np.ndarray:
    if PROJECT_BACKEND:
        return np.asarray(_project_interleave(values, INTERLEAVER_BLOCK))
    array = np.asarray(values).ravel()
    full = (len(array) // INTERLEAVER_BLOCK) * INTERLEAVER_BLOCK
    if full == 0:
        return array.copy()
    result = array[:full].reshape(-1, INTERLEAVER_BLOCK).T.ravel()
    return np.concatenate((result, array[full:])) if full < len(array) else result


def block_deinterleave(values: np.ndarray) -> np.ndarray:
    if PROJECT_BACKEND:
        return np.asarray(_project_deinterleave(values, INTERLEAVER_BLOCK))
    array = np.asarray(values).ravel()
    full = (len(array) // INTERLEAVER_BLOCK) * INTERLEAVER_BLOCK
    if full == 0:
        return array.copy()
    rows = full // INTERLEAVER_BLOCK
    result = array[:full].reshape(INTERLEAVER_BLOCK, rows).T.ravel()
    return np.concatenate((result, array[full:])) if full < len(array) else result


def _key_stream(shared_key: str, sequence: int, length: int) -> bytes:
    """Deterministic SHA-256 counter stream used for repository-style XOR whitening."""

    output = bytearray()
    counter = 0
    while len(output) < length:
        material = (
            shared_key.encode("utf-8")
            + struct.pack(">H", int(sequence) & 0xFFFF)
            + struct.pack(">I", counter)
        )
        output.extend(hashlib.sha256(material).digest())
        counter += 1
    return bytes(output[:length])


def _xor_whiten(data: bytes, shared_key: str, sequence: int) -> bytes:
    stream = _key_stream(shared_key, sequence, len(data))
    return bytes(a ^ b for a, b in zip(data, stream))


def build_packet(payload: bytes, config: DemoConfig) -> bytes:
    config.validate()
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise ValueError(f"payload is {len(payload)} bytes; maximum is {MAX_PAYLOAD_BYTES}")
    sequence = int(config.sequence) & 0xFFFF
    header = MAGIC + bytes((VERSION,)) + struct.pack(">H", sequence) + bytes((len(payload),))
    padded_plaintext = payload.ljust(MAX_PAYLOAD_BYTES, b"\x00")
    protected_payload = _xor_whiten(padded_plaintext, config.shared_key, sequence)
    crc = zlib.crc32(header + payload) & 0xFFFFFFFF
    return header + protected_payload + struct.pack(">I", crc)


def parse_packet(packet: bytes, config: DemoConfig) -> tuple[bytes, int]:
    if len(packet) != config.raw_packet_bytes:
        raise ValueError("wrong packet length")
    if packet[:2] != MAGIC or packet[2] != VERSION:
        raise ValueError("magic/version check failed")
    sequence = struct.unpack(">H", packet[3:5])[0]
    payload_length = packet[5]
    if payload_length > MAX_PAYLOAD_BYTES:
        raise ValueError("invalid payload length")
    protected = packet[6 : 6 + MAX_PAYLOAD_BYTES]
    padded_plaintext = _xor_whiten(protected, config.shared_key, sequence)
    payload = padded_plaintext[:payload_length]
    received_crc = struct.unpack(">I", packet[-4:])[0]
    calculated_crc = zlib.crc32(packet[:6] + payload) & 0xFFFFFFFF
    if received_crc != calculated_crc:
        raise ValueError("CRC-32 failed (wrong key or damaged packet)")
    return payload, sequence


def _repeat_chips(chips: np.ndarray, samples_per_chip: int) -> np.ndarray:
    return np.repeat(np.asarray(chips, dtype=np.float32), samples_per_chip).astype(np.complex64)


def build_active_waveform(payload: bytes, config: DemoConfig) -> tuple[np.ndarray, dict]:
    """Build one active burst (without the leading silent gap)."""

    packet = build_packet(payload, config)
    raw_bits = np.unpackbits(np.frombuffer(packet, dtype=np.uint8), bitorder="big")
    terminated = np.concatenate((raw_bits, np.zeros(FEC_TAIL_BITS, dtype=np.uint8)))
    coded = convolutional_encode(terminated)
    interleaved = np.asarray(block_interleave(coded), dtype=np.uint8)
    if len(interleaved) != config.coded_bits:
        raise RuntimeError("internal coded length mismatch")

    sample_index = np.arange(ACQUISITION_SAMPLES, dtype=np.float64)
    acquisition = np.exp(
        1j * 2.0 * np.pi * ACQUISITION_TONE_HZ * sample_index / config.sample_rate
    ).astype(np.complex64)
    sync = _repeat_chips(_gold_code(SYNC_CHIPS, 1777), config.samples_per_chip)
    pilot = _repeat_chips(_gold_code(PILOT_CHIPS, 9001), config.samples_per_chip)
    data_code = spreading_code(config)

    pieces: list[np.ndarray] = [acquisition, sync]
    for first in range(0, len(interleaved), DATA_BITS_PER_PILOT):
        block = interleaved[first : first + DATA_BITS_PER_PILOT]
        symbols = 1.0 - 2.0 * block.astype(np.float64)
        chips = np.outer(symbols, data_code).ravel()
        pieces.append(pilot)
        pieces.append(_repeat_chips(chips, config.samples_per_chip))
    active = (config.amplitude * np.concatenate(pieces)).astype(np.complex64)
    metadata = {
        "payload_utf8": payload.decode("utf-8", errors="replace"),
        "payload_hex": payload.hex(),
        "sequence": int(config.sequence) & 0xFFFF,
        "sample_rate": config.sample_rate,
        "samples_per_chip": config.samples_per_chip,
        "chip_rate": config.sample_rate / config.samples_per_chip,
        "code_length": config.code_length,
        "processing_gain_db": config.processing_gain_db,
        "coded_bits": config.coded_bits,
        "active_samples": len(active),
        "cycle_samples": config.gap_samples + len(active),
        "project_backend": PROJECT_BACKEND,
        "protection": "shared-key XOR whitening + convolutional FEC + interleaving + CRC-32",
    }
    return active, metadata


def build_repeating_waveform(message: str, config: DemoConfig) -> tuple[np.ndarray, dict]:
    payload = str(message).encode("utf-8")
    active, metadata = build_active_waveform(payload, config)
    gap = np.zeros(config.gap_samples, dtype=np.complex64)
    return np.concatenate((gap, active)), metadata


def _normalized_correlation(template: np.ndarray, segment: np.ndarray) -> complex:
    denominator = float(np.linalg.norm(template) * np.linalg.norm(segment)) + 1e-15
    return np.vdot(template, segment) / denominator


def _find_rising_edges(samples: np.ndarray, config: DemoConfig) -> list[int]:
    power = np.abs(samples) ** 2
    if len(power) < config.active_samples:
        return []
    width = 64
    smooth = np.convolve(power, np.ones(width) / width, mode="same")
    low = float(np.percentile(smooth, 10.0))
    high = float(np.percentile(smooth, 90.0))
    if not np.isfinite(high) or high <= low * 1.02 + 1e-12:
        return []
    threshold = low + 0.28 * (high - low)
    active = smooth > threshold
    raw_edges = np.flatnonzero(active[1:] & ~active[:-1]) + 1
    edges: list[int] = []
    minimum_spacing = max(config.gap_samples // 2, 4096)
    for edge in raw_edges:
        candidate = int(edge + width // 2)
        if not edges or candidate - edges[-1] >= minimum_spacing:
            edges.append(candidate)
    return edges


def _interpolated_samples(signal: np.ndarray, positions: np.ndarray) -> np.ndarray:
    index = np.arange(len(signal), dtype=np.float64)
    real = np.interp(positions, index, np.real(signal), left=0.0, right=0.0)
    imag = np.interp(positions, index, np.imag(signal), left=0.0, right=0.0)
    return real + 1j * imag


def _decode_candidate(
    samples: np.ndarray, rough_start: int, config: DemoConfig
) -> DecodeResult | None:
    search_radius = 96
    start = max(0, int(rough_start))
    if start + config.active_samples + search_radius > len(samples):
        return None

    tone_first = start + 128
    tone_last = start + ACQUISITION_SAMPLES - 128
    tone = samples[tone_first:tone_last]
    if len(tone) < 512:
        return None
    # Estimate the acquisition tone with a zero-padded FFT.  A simple adjacent-
    # sample phase estimate is easily biased by the exact narrow-band interferer
    # that DSSS is intended to tolerate; selecting the strongest spectral line
    # around the known acquisition frequency is much more robust.
    fft_size = 1 << int(math.ceil(math.log2(max(16_384, len(tone) * 4))))
    windowed = tone * np.hanning(len(tone))
    spectrum = np.abs(np.fft.fft(windowed, n=fft_size))
    frequencies = np.fft.fftfreq(fft_size, d=1.0 / config.sample_rate)
    distance = np.abs(
        (frequencies - ACQUISITION_TONE_HZ + config.sample_rate / 2.0)
        % config.sample_rate
        - config.sample_rate / 2.0
    )
    allowed = distance <= 100_000.0
    if not np.any(allowed):
        return None
    masked = np.where(allowed, spectrum, -np.inf)
    peak = int(np.argmax(masked))
    # Three-bin parabolic interpolation improves the residual frequency error.
    left = spectrum[(peak - 1) % fft_size]
    middle = spectrum[peak]
    right = spectrum[(peak + 1) % fft_size]
    denominator = left - 2.0 * middle + right
    fraction = 0.0 if abs(denominator) < 1e-15 else 0.5 * (left - right) / denominator
    measured_hz = frequencies[peak] + fraction * config.sample_rate / fft_size
    cfo_hz = (
        measured_hz
        - ACQUISITION_TONE_HZ
        + config.sample_rate / 2.0
    ) % config.sample_rate - config.sample_rate / 2.0

    corrected = samples.astype(np.complex128) * np.exp(
        -1j * 2.0 * np.pi * cfo_hz * np.arange(len(samples)) / config.sample_rate
    )
    sync_template = _repeat_chips(_gold_code(SYNC_CHIPS, 1777), config.samples_per_chip)
    predicted_sync = start + ACQUISITION_SAMPLES
    best_sync_score = -1.0
    best_sync_start = predicted_sync
    best_sync_corr = 0j
    for offset in range(-search_radius, search_radius + 1):
        location = predicted_sync + offset
        segment = corrected[location : location + len(sync_template)]
        if len(segment) != len(sync_template):
            continue
        correlation = _normalized_correlation(sync_template, segment)
        score = abs(correlation)
        if score > best_sync_score:
            best_sync_score = score
            best_sync_start = location
            best_sync_corr = correlation
    if best_sync_score < 0.32:
        return None

    pilot_template = _repeat_chips(_gold_code(PILOT_CHIPS, 9001), config.samples_per_chip)
    data_code = spreading_code(config)
    cursor = best_sync_start + len(sync_template)
    soft_interleaved: list[np.ndarray] = []
    pilot_scores: list[float] = []
    bits_remaining = config.coded_bits

    for _block_index in range(config.data_blocks):
        block_bits = min(DATA_BITS_PER_PILOT, bits_remaining)
        best_score = -1.0
        best_start = cursor
        best_corr = 0j
        for offset in range(-24, 25):
            location = cursor + offset
            segment = corrected[location : location + len(pilot_template)]
            if len(segment) != len(pilot_template):
                continue
            correlation = _normalized_correlation(pilot_template, segment)
            score = abs(correlation)
            if score > best_score:
                best_score = score
                best_start = location
                best_corr = correlation
        if best_score < 0.22:
            return None
        pilot_scores.append(best_score)

        data_start = best_start + len(pilot_template)
        chip_count = block_bits * config.code_length
        centers = (
            data_start
            + np.arange(chip_count, dtype=np.float64) * config.samples_per_chip
            + (config.samples_per_chip - 1.0) / 2.0
        )
        chip_values = _interpolated_samples(corrected, centers) * np.exp(-1j * np.angle(best_corr))
        soft = np.real(chip_values).reshape(block_bits, config.code_length) @ data_code
        soft_interleaved.append(np.asarray(soft, dtype=np.float64))
        cursor = data_start + chip_count * config.samples_per_chip
        bits_remaining -= block_bits

    interleaved_soft = np.concatenate(soft_interleaved)[: config.coded_bits]
    coded_soft = np.asarray(block_deinterleave(interleaved_soft), dtype=np.float64)
    decoded = convolutional_decode_soft(coded_soft)
    if len(decoded) < config.raw_packet_bytes * 8:
        return None
    packet_bits = decoded[: config.raw_packet_bytes * 8].astype(np.uint8)
    packet = np.packbits(packet_bits, bitorder="big").tobytes()
    try:
        payload, sequence = parse_packet(packet, config)
        message = payload.decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None

    return DecodeResult(
        message=message,
        payload_hex=payload.hex(),
        sequence=sequence,
        crc_ok=True,
        sync_score=float(best_sync_score),
        minimum_pilot_score=float(min(pilot_scores)),
        cfo_hz=float(cfo_hz),
        sample_start=int(start),
        sample_end=int(cursor),
        timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
    )


def decode_capture(samples: np.ndarray, config: DemoConfig) -> DecodeResult | None:
    """Find and decode the first valid burst in an arbitrary complex64 capture."""

    config.validate()
    signal = np.asarray(samples, dtype=np.complex64).ravel()
    edges = _find_rising_edges(signal, config)
    for edge in edges:
        # Moving-power edge placement varies with SNR; try a small set around it.
        for adjustment in (0, -32, 32, -64, 64):
            result = _decode_candidate(signal, edge + adjustment, config)
            if result is not None:
                return result
    return None


class StreamingDecoder:
    """Small state holder used inside the RX Embedded Python Block."""

    def __init__(
        self,
        config: DemoConfig,
        output_text_path: str = "decoded_message.txt",
        output_json_path: str = "rx_status.json",
    ) -> None:
        self.config = config
        self.output_text_path = Path(output_text_path)
        self.output_json_path = Path(output_json_path)
        self.buffer = np.empty(0, dtype=np.complex64)
        self.result: DecodeResult | None = None
        self.attempts = 0

    def push(self, samples: np.ndarray) -> DecodeResult | None:
        if self.result is not None:
            return self.result
        incoming = np.asarray(samples, dtype=np.complex64).ravel()
        if len(incoming):
            self.buffer = np.concatenate((self.buffer, incoming))
        if len(self.buffer) < config_minimum_capture(self.config):
            return None
        self.attempts += 1
        result = decode_capture(self.buffer, self.config)
        if result is not None:
            self.result = result
            self._write_result(result)
            return result
        maximum = self.config.cycle_samples * 3
        if len(self.buffer) > maximum:
            self.buffer = self.buffer[-self.config.cycle_samples * 2 :]
        return None

    def _write_result(self, result: DecodeResult) -> None:
        self.output_text_path.write_text(result.message + "\n", encoding="utf-8")
        status = result.to_dict()
        status.update(
            {
                "status": "SUCCESS",
                "attempts": self.attempts,
                "processing_gain_db": self.config.processing_gain_db,
                "project_backend": PROJECT_BACKEND,
            }
        )
        self.output_json_path.write_text(
            json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def config_minimum_capture(config: DemoConfig) -> int:
    # One full active burst plus enough preceding samples to expose a rising edge.
    return config.active_samples + min(config.gap_samples, 8192)


def simulate_channel(
    waveform: np.ndarray,
    config: DemoConfig,
    repetitions: int = 3,
    cfo_hz: float = 18_000.0,
    snr_db: float = 2.0,
    tone_interference_amplitude: float = 0.08,
    seed: int = 2026,
) -> np.ndarray:
    """Deterministic offline channel used by ``self_test.py``."""

    rng = np.random.default_rng(seed)
    prefix = np.zeros(config.gap_samples // 2, dtype=np.complex64)
    signal = np.concatenate((prefix, np.tile(waveform, repetitions))).astype(np.complex128)
    index = np.arange(len(signal), dtype=np.float64)
    signal *= np.exp(1j * 2.0 * np.pi * cfo_hz * index / config.sample_rate + 0.73j)
    if tone_interference_amplitude > 0:
        signal += tone_interference_amplitude * np.exp(
            1j * (2.0 * np.pi * 103_000.0 * index / config.sample_rate + 1.1)
        )
    active_power = config.amplitude**2
    noise_power = active_power / (10.0 ** (snr_db / 10.0))
    noise = math.sqrt(noise_power / 2.0) * (
        rng.standard_normal(len(signal)) + 1j * rng.standard_normal(len(signal))
    )
    return (signal + noise).astype(np.complex64)
