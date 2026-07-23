"""
Contest DSSS Codec — 比赛级抗干扰通信编码
============================================
基于 demo_codec.py 改进：
  - SF=127 Gold 码 (21dB 处理增益 vs demo 的 31=14.9dB)
  - 文件分帧协议 (支持大文件分块传输)
  - 16 通道跳频 (2.405-2.48 GHz)
  - 级联 FEC: 卷积码 K=7,R=1/2 + 可选的 RS 外码
  - 511-chip 同步序列 (比 demo 的 255 更抗干扰)
  - 每队独立 Gold 码 (team_id 选码)
  - CRC-32 逐包校验
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import time
import zlib
from typing import Optional

import numpy as np

# ─── Try to use V8 project backend, fallback to built-in ───
_REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
_SRC = _REPOSITORY_ROOT / "V8" / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

try:
    from wireless_competition.adversarial.dsss import generate_spreading_code as _proj_spread
    from wireless_competition.tx.fec import convolutional_encode as _proj_conv_enc
    from wireless_competition.tx.fec import convolutional_decode_soft as _proj_conv_dec_soft
    from wireless_competition.tx.interleaver import block_interleave as _proj_interleave
    from wireless_competition.tx.interleaver import block_deinterleave as _proj_deinterleave
    PROJECT_BACKEND = True
except Exception:
    _proj_spread = None; _proj_conv_enc = None
    _proj_conv_dec_soft = None; _proj_interleave = None
    _proj_deinterleave = None
    PROJECT_BACKEND = False

# ═══════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════

MAGIC = b"C1"             # Contest v1 magic
VERSION = 1
FEC_TAIL_BITS = 6
INTERLEAVER_BLOCK = 18
DATA_BITS_PER_PILOT = 64
ACQUISITION_TONE_HZ = 62_500.0
ACQUISITION_SAMPLES = 4096   # 2x demo for better CFO in interference
SYNC_CHIPS = 511             # 2x demo
PILOT_CHIPS = 255            # 2x demo
MAX_PAYLOAD_BYTES = 512   # file chunk size (burst ~3.5s @ SF=127)

# Frequency hopping: 16 channels, 5 MHz spacing, 2.4 GHz ISM band
HOP_CHANNELS = [
    2_405_000_000, 2_410_000_000, 2_415_000_000, 2_420_000_000,
    2_425_000_000, 2_430_000_000, 2_435_000_000, 2_440_000_000,
    2_445_000_000, 2_450_000_000, 2_455_000_000, 2_460_000_000,
    2_465_000_000, 2_470_000_000, 2_475_000_000, 2_480_000_000,
]
HOP_DWELL_S = 0.05  # 50 ms per hop (must be > one packet duration)
HOP_GUARD_S  = 0.005  # 5 ms guard between hops


@dataclass(frozen=True)
class ContestConfig:
    """Parameters that MUST match between TX and RX."""

    sample_rate: int = 1_000_000
    samples_per_chip: int = 4
    code_length: int = 127           # SF=127 → 21 dB gain
    team_id: int = 0                  # determines Gold code pair
    shared_key: str = "contest-key-2026"
    amplitude: float = 0.30
    gap_samples: int = 50_000         # gap between bursts (longer for hop settling)
    sequence: int = 1
    hop_enabled: bool = True          # enable frequency hopping
    hop_channels: list[int] = field(default_factory=lambda: list(HOP_CHANNELS))
    hop_dwell_samples: int = 0        # computed below
    hop_guard_samples: int = 0        # computed below

    def __post_init__(self):
        object.__setattr__(self, 'hop_dwell_samples',
                           int(self.hop_dwell_s * self.sample_rate))
        object.__setattr__(self, 'hop_guard_samples',
                           int(self.hop_guard_s * self.sample_rate))

    @property
    def hop_dwell_s(self) -> float: return HOP_DWELL_S

    @property
    def hop_guard_s(self) -> float: return HOP_GUARD_S

    def validate(self) -> None:
        if self.sample_rate < 520_834:
            raise ValueError("sample_rate too low")
        if self.samples_per_chip < 2:
            raise ValueError("samples_per_chip must be >= 2")
        if self.code_length < 31:
            raise ValueError("code_length must be >= 31 for contest")
        if not self.shared_key:
            raise ValueError("shared_key required")
        if not (0.01 <= self.amplitude <= 0.8):
            raise ValueError("amplitude [0.01, 0.8]")

    @property
    def frame_header_bytes(self) -> int:
        # magic(2) + version(1) + file_id(4) + seq(2) + total(2) + payload_len(2) = 13
        return 2 + 1 + 4 + 2 + 2 + 2

    @property
    def raw_packet_bytes(self) -> int:
        return self.frame_header_bytes + MAX_PAYLOAD_BYTES + 4  # + CRC32

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
        return (ACQUISITION_SAMPLES + self.sync_samples
                + self.data_blocks * self.pilot_samples + data_samples)

    @property
    def cycle_samples(self) -> int:
        return self.gap_samples + self.active_samples

    @property
    def processing_gain_db(self) -> float:
        return 10.0 * math.log10(self.code_length)

    def hop_freq(self, hop_index: int) -> int:
        """Get center frequency for a given hop index."""
        return self.hop_channels[hop_index % len(self.hop_channels)]

    def hop_for_sample(self, sample_index: int) -> int:
        """Which hop index a given sample belongs to."""
        period = self.hop_dwell_samples + self.hop_guard_samples
        return sample_index // period


# ═══════════════════════════════════════════════════════════════
# Gold Code Generation
# ═══════════════════════════════════════════════════════════════

def _gold_code(length: int, seed: int) -> np.ndarray:
    """10-bit LFSR Gold code generator."""
    rng = np.random.default_rng(seed)
    reg1 = int(rng.integers(1, 2**10, dtype=np.int64))
    reg2 = int(rng.integers(1, 2**10, dtype=np.int64))
    code = np.zeros(int(length), dtype=np.int8)
    for idx in range(int(length)):
        b1 = ((reg1 >> 9) ^ (reg1 >> 5) ^ reg1) & 1
        reg1 = ((reg1 << 1) | b1) & 0x3FF
        b2 = ((reg2 >> 9) ^ (reg2 >> 7) ^ (reg2 >> 3) ^ reg2) & 1
        reg2 = ((reg2 << 1) | b2) & 0x3FF
        code[idx] = 1 if (b1 ^ b2) == 0 else -1
    return code


def spreading_code(config: ContestConfig) -> np.ndarray:
    """Get team-specific spreading code."""
    if PROJECT_BACKEND:
        return np.asarray(
            _proj_spread(config.code_length, config.team_id), dtype=np.float64)
    return _gold_code(config.code_length, 42 + config.team_id * 100).astype(np.float64)


# ═══════════════════════════════════════════════════════════════
# Convolutional FEC (K=7, R=1/2, NASA-DSN)
# ═══════════════════════════════════════════════════════════════

def _conv_enc_fallback(bits: np.ndarray) -> np.ndarray:
    bits = np.asarray(bits, dtype=np.uint8).ravel()
    enc = np.zeros(len(bits) * 2, dtype=np.uint8)
    state = 0
    for i, bit in enumerate(bits):
        b = int(bit)
        b5, b4, b3 = (state >> 5) & 1, (state >> 4) & 1, (state >> 3) & 1
        b1, b0 = (state >> 1) & 1, state & 1
        enc[2 * i] = b ^ b5 ^ b4 ^ b3 ^ b0
        enc[2 * i + 1] = b ^ b4 ^ b3 ^ b1 ^ b0
        state = ((state << 1) | b) & 0x3F
    return enc


def conv_encode(bits: np.ndarray) -> np.ndarray:
    if PROJECT_BACKEND:
        return np.asarray(_proj_conv_enc(bits), dtype=np.uint8)
    return _conv_enc_fallback(bits)


# Soft Viterbi decoder trellis (pre-built)
_TRELLIS_NS = np.zeros((64, 2), dtype=np.int16)
_TRELLIS_OUT = np.zeros((64, 2, 2), dtype=np.uint8)
for _state in range(64):
    for _bit in (0, 1):
        _b5, _b4, _b3 = (_state >> 5) & 1, (_state >> 4) & 1, (_state >> 3) & 1
        _b1, _b0 = (_state >> 1) & 1, _state & 1
        _TRELLIS_OUT[_state, _bit, 0] = _bit ^ _b5 ^ _b4 ^ _b3 ^ _b0
        _TRELLIS_OUT[_state, _bit, 1] = _bit ^ _b4 ^ _b3 ^ _b1 ^ _b0
        _TRELLIS_NS[_state, _bit] = ((_state << 1) | _bit) & 0x3F


def _conv_dec_soft_fallback(llr: np.ndarray) -> np.ndarray:
    vals = np.asarray(llr, dtype=np.float64).ravel()
    if len(vals) % 2:
        raise ValueError("soft Viterbi: even length required")
    steps = len(vals) // 2
    metrics = np.full(64, np.inf); metrics[0] = 0.0
    prev_st = np.zeros((steps, 64), dtype=np.int16)
    prev_bit = np.zeros((steps, 64), dtype=np.uint8)
    for step in range(steps):
        pair = vals[2*step:2*step+2]
        new_m = np.full(64, np.inf)
        for st in range(64):
            if not np.isfinite(metrics[st]): continue
            for bit in (0, 1):
                expected = _TRELLIS_OUT[st, bit]
                cost = float(np.sum(-0.5*(1.0-2.0*expected)*pair))
                dst = int(_TRELLIS_NS[st, bit])
                cand = metrics[st] + cost
                if cand < new_m[dst]:
                    new_m[dst] = cand
                    prev_st[step, dst] = st
                    prev_bit[step, dst] = bit
        metrics = new_m
    st = 0 if np.isfinite(metrics[0]) else int(np.argmin(metrics))
    dec = np.zeros(steps, dtype=np.uint8)
    for step in range(steps-1, -1, -1):
        dec[step] = prev_bit[step, st]
        st = int(prev_st[step, st])
    return dec


def conv_decode_soft(llr: np.ndarray) -> np.ndarray:
    if PROJECT_BACKEND:
        return np.asarray(_proj_conv_dec_soft(llr), dtype=np.uint8)
    return _conv_dec_soft_fallback(llr)


# ═══════════════════════════════════════════════════════════════
# Interleaving
# ═══════════════════════════════════════════════════════════════

def block_interleave(vals: np.ndarray) -> np.ndarray:
    if PROJECT_BACKEND:
        return np.asarray(_proj_interleave(vals, INTERLEAVER_BLOCK))
    arr = np.asarray(vals).ravel()
    full = (len(arr)//INTERLEAVER_BLOCK)*INTERLEAVER_BLOCK
    if full == 0: return arr.copy()
    res = arr[:full].reshape(-1, INTERLEAVER_BLOCK).T.ravel()
    return np.concatenate((res, arr[full:])) if full < len(arr) else res


def block_deinterleave(vals: np.ndarray) -> np.ndarray:
    if PROJECT_BACKEND:
        return np.asarray(_proj_deinterleave(vals, INTERLEAVER_BLOCK))
    arr = np.asarray(vals).ravel()
    full = (len(arr)//INTERLEAVER_BLOCK)*INTERLEAVER_BLOCK
    if full == 0: return arr.copy()
    rows = full//INTERLEAVER_BLOCK
    res = arr[:full].reshape(INTERLEAVER_BLOCK, rows).T.ravel()
    return np.concatenate((res, arr[full:])) if full < len(arr) else res


# ═══════════════════════════════════════════════════════════════
# SHA-256 XOR Whitening
# ═══════════════════════════════════════════════════════════════

def _key_stream(key: str, seq: int, file_id: int, length: int) -> bytes:
    out = bytearray(); ctr = 0
    while len(out) < length:
        mat = (key.encode("utf-8") + struct.pack(">H", seq & 0xFFFF)
               + struct.pack(">I", file_id & 0xFFFFFFFF)
               + struct.pack(">I", ctr))
        out.extend(hashlib.sha256(mat).digest()); ctr += 1
    return bytes(out[:length])


def _xor_whiten(data: bytes, key: str, seq: int, file_id: int) -> bytes:
    stream = _key_stream(key, seq, file_id, len(data))
    return bytes(a ^ b for a, b in zip(data, stream))


# ═══════════════════════════════════════════════════════════════
# File Framing Protocol
# ═══════════════════════════════════════════════════════════════

@dataclass
class FileManifest:
    file_id: int
    file_name: str
    total_blocks: int
    original_size: int
    sha256: str

    def to_dict(self) -> dict: return asdict(self)


def prepare_file_transfer(file_path: Path, config: ContestConfig) -> tuple[
    list[bytes], FileManifest]:
    """Split a file into packets ready for DSSS encoding."""
    data = file_path.read_bytes()
    file_id = int(hashlib.sha256(
        file_path.name.encode() + data[:64]).hexdigest()[:8], 16) & 0xFFFFFFFF
    sha = hashlib.sha256(data).hexdigest()
    block_size = MAX_PAYLOAD_BYTES
    total_blocks = math.ceil(len(data) / block_size)
    manifest = FileManifest(
        file_id=file_id, file_name=file_path.name,
        total_blocks=total_blocks, original_size=len(data), sha256=sha)

    packets = []
    for seq in range(total_blocks):
        start = seq * block_size
        payload = data[start:start + block_size]
        packet = build_packet(payload, seq, total_blocks, file_id, config)
        packets.append(packet)
    return packets, manifest


def build_packet(payload: bytes, seq: int, total: int, file_id: int,
                 config: ContestConfig) -> bytes:
    """Build a single frame packet: header + whitened_payload + CRC32."""
    config.validate()
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise ValueError(f"payload too large: {len(payload)} > {MAX_PAYLOAD_BYTES}")
    seq16 = seq & 0xFFFF; total16 = total & 0xFFFF
    header = (MAGIC + bytes((VERSION,)) + struct.pack(">I", file_id)
              + struct.pack(">H", seq16) + struct.pack(">H", total16)
              + struct.pack(">H", len(payload)))
    padded = payload.ljust(MAX_PAYLOAD_BYTES, b"\x00")
    protected = _xor_whiten(padded, config.shared_key, seq, file_id)
    crc = zlib.crc32(header + payload) & 0xFFFFFFFF
    return header + protected + struct.pack(">I", crc)


def parse_packet(packet: bytes, config: ContestConfig) -> tuple[bytes, int, int, int]:
    """Parse a received frame packet. Returns (payload, seq, total, file_id)."""
    if len(packet) != config.raw_packet_bytes:
        raise ValueError("wrong packet length")
    if packet[:2] != MAGIC or packet[2] != VERSION:
        raise ValueError("magic/version mismatch")
    file_id = struct.unpack(">I", packet[3:7])[0]
    seq = struct.unpack(">H", packet[7:9])[0]
    total = struct.unpack(">H", packet[9:11])[0]
    payload_len = struct.unpack(">H", packet[11:13])[0]
    if payload_len > MAX_PAYLOAD_BYTES:
        raise ValueError("invalid payload length")
    header = packet[:13]
    protected = packet[13:13 + MAX_PAYLOAD_BYTES]
    padded = _xor_whiten(protected, config.shared_key, seq, file_id)
    payload = padded[:payload_len]
    rx_crc = struct.unpack(">I", packet[-4:])[0]
    calc_crc = zlib.crc32(header + payload) & 0xFFFFFFFF
    if rx_crc != calc_crc:
        raise ValueError("CRC-32 failed")
    return payload, seq, total, file_id


# ═══════════════════════════════════════════════════════════════
# DSSS Waveform Building
# ═══════════════════════════════════════════════════════════════

def _repeat_chips(chips: np.ndarray, spc: int) -> np.ndarray:
    return np.repeat(np.asarray(chips, dtype=np.float32), spc).astype(np.complex64)


def build_active_waveform(packet_bytes: bytes, config: ContestConfig
                          ) -> tuple[np.ndarray, dict]:
    """Build one active DSSS burst (acquisition + sync + data+pilots)."""
    raw_bits = np.unpackbits(np.frombuffer(packet_bytes, dtype=np.uint8), bitorder="big")
    terminated = np.concatenate((raw_bits, np.zeros(FEC_TAIL_BITS, dtype=np.uint8)))
    coded = conv_encode(terminated)
    interleaved = np.asarray(block_interleave(coded), dtype=np.uint8)
    if len(interleaved) != config.coded_bits:
        raise RuntimeError("internal coded length mismatch")

    # Acquisition tone
    t = np.arange(ACQUISITION_SAMPLES, dtype=np.float64)
    acq = np.exp(1j * 2.0 * np.pi * ACQUISITION_TONE_HZ * t / config.sample_rate
                ).astype(np.complex64)

    sync = _repeat_chips(_gold_code(SYNC_CHIPS, 1777), config.samples_per_chip)
    pilot = _repeat_chips(_gold_code(PILOT_CHIPS, 9001), config.samples_per_chip)
    data_code = spreading_code(config)

    pieces: list[np.ndarray] = [acq, sync]
    for first in range(0, len(interleaved), DATA_BITS_PER_PILOT):
        block = interleaved[first:first + DATA_BITS_PER_PILOT]
        syms = 1.0 - 2.0 * block.astype(np.float64)
        chips = np.outer(syms, data_code).ravel()
        pieces.append(pilot)
        pieces.append(_repeat_chips(chips, config.samples_per_chip))

    active = (config.amplitude * np.concatenate(pieces)).astype(np.complex64)
    meta = {
        "packet_bytes": len(packet_bytes),
        "sample_rate": config.sample_rate,
        "code_length": config.code_length,
        "processing_gain_db": config.processing_gain_db,
        "active_samples": len(active),
        "sync_chips": SYNC_CHIPS,
        "pilot_chips": PILOT_CHIPS,
        "backend": "project" if PROJECT_BACKEND else "fallback",
    }
    return active, meta


def build_burst(packet_bytes: bytes, config: ContestConfig) -> np.ndarray:
    """One burst = gap + active waveform."""
    active, _ = build_active_waveform(packet_bytes, config)
    gap = np.zeros(config.gap_samples, dtype=np.complex64)
    return np.concatenate((gap, active))


# ═══════════════════════════════════════════════════════════════
# Receiver: Burst Detection + Decoding
# ═══════════════════════════════════════════════════════════════

def _norm_corr(template: np.ndarray, segment: np.ndarray) -> complex:
    denom = float(np.linalg.norm(template) * np.linalg.norm(segment)) + 1e-15
    return np.vdot(template, segment) / denom


def _find_rising_edges(samples: np.ndarray, config: ContestConfig) -> list[int]:
    power = np.abs(samples) ** 2
    if len(power) < config.active_samples:
        return []
    width = 128
    smooth = np.convolve(power, np.ones(width)/width, mode="same")
    low = float(np.percentile(smooth, 10.0))
    high = float(np.percentile(smooth, 90.0))
    if not np.isfinite(high) or high <= low * 1.02 + 1e-12:
        return []
    threshold = low + 0.25 * (high - low)
    active = smooth > threshold
    raw_edges = np.flatnonzero(active[1:] & ~active[:-1]) + 1
    edges: list[int] = []
    min_spacing = max(config.gap_samples // 2, 4096)
    for edge in raw_edges:
        cand = int(edge + width // 2)
        if not edges or cand - edges[-1] >= min_spacing:
            edges.append(cand)
    return edges


def _interpolated_samples(signal: np.ndarray, positions: np.ndarray) -> np.ndarray:
    idx = np.arange(len(signal), dtype=np.float64)
    re = np.interp(positions, idx, np.real(signal), left=0.0, right=0.0)
    im = np.interp(positions, idx, np.imag(signal), left=0.0, right=0.0)
    return re + 1j * im


@dataclass
class DecodeResult:
    payload: bytes
    seq: int
    total: int
    file_id: int
    crc_ok: bool
    sync_score: float
    min_pilot_score: float
    cfo_hz: float
    sample_start: int
    sample_end: int
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["payload_hex"] = self.payload.hex()
        return d


def _decode_candidate(samples: np.ndarray, rough_start: int,
                      config: ContestConfig) -> Optional[DecodeResult]:
    search_radius = 128
    start = max(0, int(rough_start))
    if start + config.active_samples + search_radius > len(samples):
        return None

    # ── CFO estimation via acquisition tone FFT ──
    tone_first = start + 256
    tone_last = start + ACQUISITION_SAMPLES - 256
    tone = samples[tone_first:tone_last]
    if len(tone) < 512:
        return None
    fft_size = 1 << int(math.ceil(math.log2(max(16_384, len(tone) * 4))))
    windowed = tone * np.hanning(len(tone))
    spectrum = np.abs(np.fft.fft(windowed, n=fft_size))
    freqs = np.fft.fftfreq(fft_size, d=1.0 / config.sample_rate)
    dist = np.abs((freqs - ACQUISITION_TONE_HZ + config.sample_rate/2.0)
                   % config.sample_rate - config.sample_rate/2.0)
    allowed = dist <= 150_000.0
    if not np.any(allowed):
        return None
    masked = np.where(allowed, spectrum, -np.inf)
    peak = int(np.argmax(masked))
    left = spectrum[(peak-1)%fft_size]; right = spectrum[(peak+1)%fft_size]
    denom_parab = left - 2.0*spectrum[peak] + right
    frac = 0.0 if abs(denom_parab)<1e-15 else 0.5*(left-right)/denom_parab
    measured_hz = freqs[peak] + frac * config.sample_rate / fft_size
    cfo_hz = ((measured_hz - ACQUISITION_TONE_HZ + config.sample_rate/2.0)
              % config.sample_rate - config.sample_rate/2.0)

    corrected = samples.astype(np.complex128) * np.exp(
        -1j * 2.0 * np.pi * cfo_hz * np.arange(len(samples)) / config.sample_rate)

    # ── Sync correlation ──
    sync_tmpl = _repeat_chips(_gold_code(SYNC_CHIPS, 1777), config.samples_per_chip)
    predicted_sync = start + ACQUISITION_SAMPLES
    best_ss, best_sl, best_sc = -1.0, predicted_sync, 0j
    for off in range(-search_radius, search_radius+1):
        loc = predicted_sync + off
        seg = corrected[loc:loc+len(sync_tmpl)]
        if len(seg) != len(sync_tmpl): continue
        c = _norm_corr(sync_tmpl, seg); s = abs(c)
        if s > best_ss: best_ss, best_sl, best_sc = s, loc, c
    if best_ss < 0.30:
        return None

    # ── Pilot tracking + data despread ──
    pilot_tmpl = _repeat_chips(_gold_code(PILOT_CHIPS, 9001), config.samples_per_chip)
    data_code = spreading_code(config)
    cursor = best_sl + len(sync_tmpl)
    soft_interleaved: list[np.ndarray] = []
    pilot_scores: list[float] = []
    bits_remaining = config.coded_bits

    for _ in range(config.data_blocks):
        block_bits = min(DATA_BITS_PER_PILOT, bits_remaining)
        best_ps, best_pl, best_pc = -1.0, cursor, 0j
        for off in range(-32, 33):
            loc = cursor + off
            seg = corrected[loc:loc+len(pilot_tmpl)]
            if len(seg) != len(pilot_tmpl): continue
            c = _norm_corr(pilot_tmpl, seg); s = abs(c)
            if s > best_ps: best_ps, best_pl, best_pc = s, loc, c
        if best_ps < 0.20:
            return None
        pilot_scores.append(best_ps)

        data_start = best_pl + len(pilot_tmpl)
        chip_count = block_bits * config.code_length
        centers = (data_start + np.arange(chip_count, dtype=np.float64)
                   * config.samples_per_chip + (config.samples_per_chip-1.0)/2.0)
        chip_vals = (_interpolated_samples(corrected, centers)
                     * np.exp(-1j * np.angle(best_pc)))
        soft = np.real(chip_vals).reshape(block_bits, config.code_length) @ data_code
        soft_interleaved.append(np.asarray(soft, dtype=np.float64))
        cursor = data_start + chip_count * config.samples_per_chip
        bits_remaining -= block_bits

    # ── Deinterleave → Viterbi → Parse ──
    ileaved = np.concatenate(soft_interleaved)[:config.coded_bits]
    coded_soft = np.asarray(block_deinterleave(ileaved), dtype=np.float64)
    decoded = conv_decode_soft(coded_soft)
    if len(decoded) < config.raw_packet_bytes * 8:
        return None
    packet_bits = decoded[:config.raw_packet_bytes*8].astype(np.uint8)
    packet = np.packbits(packet_bits, bitorder="big").tobytes()
    try:
        payload, seq, total, file_id = parse_packet(packet, config)
    except (ValueError, UnicodeDecodeError):
        return None

    return DecodeResult(
        payload=payload, seq=seq, total=total, file_id=file_id,
        crc_ok=True, sync_score=float(best_ss),
        min_pilot_score=float(min(pilot_scores)),
        cfo_hz=float(cfo_hz), sample_start=int(start), sample_end=int(cursor))


def decode_capture(samples: np.ndarray, config: ContestConfig) -> list[DecodeResult]:
    """Find and decode ALL valid bursts in a complex64 capture."""
    config.validate()
    signal = np.asarray(samples, dtype=np.complex64).ravel()
    edges = _find_rising_edges(signal, config)
    results: list[DecodeResult] = []
    seen: set[tuple[int, int]] = set()  # (file_id, seq) dedup
    for edge in edges:
        for adj in (0, -48, 48, -96, 96):
            r = _decode_candidate(signal, edge + adj, config)
            if r is not None:
                key = (r.file_id, r.seq)
                if key not in seen:
                    seen.add(key)
                    results.append(r)
                break
    return results


# ═══════════════════════════════════════════════════════════════
# Streaming Decoder (for GRC Embedded Python Block)
# ═══════════════════════════════════════════════════════════════

class StreamingDecoder:
    """State holder for GRC RX Embedded Python Block."""

    def __init__(self, config: ContestConfig,
                 output_dir: str = ".") -> None:
        self.config = config
        self.output_dir = Path(output_dir)
        self.buffer = np.empty(0, dtype=np.complex64)
        self.results: dict[tuple[int, int], bytes] = {}  # (file_id, seq) → payload
        self.file_metas: dict[int, tuple[int, str]] = {}  # file_id → (total, sha256)
        self.attempts = 0
        self._found_something = False

    def push(self, samples: np.ndarray) -> Optional[list[DecodeResult]]:
        incoming = np.asarray(samples, dtype=np.complex64).ravel()
        if len(incoming):
            self.buffer = np.concatenate((self.buffer, incoming))
        min_capture = self.config.active_samples + min(self.config.gap_samples, 8192)
        if len(self.buffer) < min_capture:
            return None
        self.attempts += 1
        results = decode_capture(self.buffer, self.config)
        if results:
            self._found_something = True
            for r in results:
                key = (r.file_id, r.seq)
                if key not in self.results:
                    self.results[key] = r.payload
                    self.file_metas[r.file_id] = (r.total, "")
            # Slide window forward
            if len(self.buffer) > self.config.cycle_samples * 3:
                self.buffer = self.buffer[-self.config.cycle_samples * 2:]
            return results
        # Slide window to prevent growing forever
        max_buf = self.config.cycle_samples * 4
        if len(self.buffer) > max_buf:
            self.buffer = self.buffer[-max_buf:]
        return None

    def assemble_file(self, file_id: int) -> Optional[bytes]:
        """Try to assemble complete file from received packets."""
        if file_id not in self.file_metas:
            return None
        total, _ = self.file_metas[file_id]
        packets = [(seq, self.results.get((file_id, seq)))
                   for seq in range(total)]
        received = [(s, p) for s, p in packets if p is not None]
        if len(received) < total:
            return None  # incomplete
        return b"".join(p for _, p in sorted(received))

    def all_complete_files(self) -> dict[int, bytes]:
        """Get all files that are fully received."""
        complete = {}
        for fid in list(self.file_metas.keys()):
            data = self.assemble_file(fid)
            if data is not None:
                complete[fid] = data
        return complete


def config_min_capture(config: ContestConfig) -> int:
    return config.active_samples + min(config.gap_samples, 8192)
