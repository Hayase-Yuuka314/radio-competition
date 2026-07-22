import json
from pathlib import Path
import struct
import zlib
import numpy as np
from gnuradio import gr

PREAMBLE_BITS = 64
SYNC_BYTES = bytes.fromhex("DDAA55D3")
SYNC_BITS = np.unpackbits(np.frombuffer(SYNC_BYTES, dtype=np.uint8), bitorder="big")
PREAMBLE = (np.arange(PREAMBLE_BITS, dtype=np.uint8) & 1)
MAX_PAYLOAD_BYTES = 64


def _symbol_averages(prefix, start, count, samples_per_symbol):
    guard = max(4, int(0.20 * samples_per_symbol))
    numbers = np.arange(count, dtype=np.int64)
    begins = start + numbers * samples_per_symbol + guard
    ends = start + (numbers + 1) * samples_per_symbol - guard
    if begins[0] < 0 or ends[-1] >= len(prefix):
        return None
    return (prefix[ends] - prefix[begins]) / (ends - begins)


class blk(gr.sync_block):
    """Burst detector and 2-FSK text receiver with CRC-32 checking."""

    def __init__(self, sample_rate=1000000, samples_per_symbol=100,
                 deviation_hz=75000.0, output_text_path="received_text.txt",
                 output_status_path="rx_status.json"):
        gr.sync_block.__init__(
            self, name="Simple 2-FSK text receiver",
            in_sig=[np.complex64], out_sig=None)
        self.sample_rate = int(sample_rate)
        self.samples_per_symbol = int(samples_per_symbol)
        self.deviation_hz = float(deviation_hz)
        self.output_text_path = Path(str(output_text_path))
        self.output_status_path = Path(str(output_status_path))
        self.buffer = np.empty(0, dtype=np.complex64)
        self.result = None
        self.last_attempt_size = 0

    def start(self):
        print("[SIMPLE RX] Waiting for a 2-FSK text packet...")
        return True

    def _find_edges(self, samples):
        power = np.abs(samples) ** 2
        if len(power) < 30000:
            return []
        width = 64
        smooth = np.convolve(power, np.ones(width) / width, mode="same")
        low = float(np.percentile(smooth, 10))
        high = float(np.percentile(smooth, 90))
        if high <= low * 1.05 + 1e-12:
            return []
        threshold = low + 0.30 * (high - low)
        active = smooth > threshold
        raw = np.flatnonzero(active[1:] & ~active[:-1]) + 1
        edges = []
        for value in raw:
            candidate = int(value + width // 2)
            if not edges or candidate - edges[-1] > 12000:
                edges.append(candidate)
        return edges

    def _decode_candidate(self, samples, rough_start):
        instantaneous = np.angle(np.conj(samples[:-1]) * samples[1:])
        instantaneous *= self.sample_rate / (2.0 * np.pi)
        prefix = np.concatenate(([0.0], np.cumsum(instantaneous, dtype=np.float64)))

        best = None
        for adjustment in range(-96, 97):
            start = int(rough_start + adjustment)
            values = _symbol_averages(
                prefix, start, PREAMBLE_BITS, self.samples_per_symbol)
            if values is None:
                continue
            zero_frequency = float(np.median(values[PREAMBLE == 0]))
            one_frequency = float(np.median(values[PREAMBLE == 1]))
            separation = one_frequency - zero_frequency
            if separation < self.deviation_hz:
                continue
            middle = 0.5 * (zero_frequency + one_frequency)
            decided = (values > middle).astype(np.uint8)
            matches = int(np.count_nonzero(decided == PREAMBLE))
            score = (matches, separation)
            if best is None or score > best[0]:
                best = (score, start, zero_frequency, one_frequency)
        if best is None or best[0][0] < 60:
            return None

        _, start, zero_frequency, one_frequency = best
        middle = 0.5 * (zero_frequency + one_frequency)
        fixed_bits = PREAMBLE_BITS + len(SYNC_BITS) + 8
        header_values = _symbol_averages(
            prefix, start, fixed_bits, self.samples_per_symbol)
        if header_values is None:
            return None
        header_bits = (header_values > middle).astype(np.uint8)
        if not np.array_equal(
                header_bits[PREAMBLE_BITS:PREAMBLE_BITS + len(SYNC_BITS)],
                SYNC_BITS):
            return None
        length_first = PREAMBLE_BITS + len(SYNC_BITS)
        payload_length = int(np.packbits(
            header_bits[length_first:length_first + 8], bitorder="big")[0])
        if payload_length > MAX_PAYLOAD_BYTES:
            return None

        total_bits = PREAMBLE_BITS + len(SYNC_BITS) + (1 + payload_length + 4) * 8
        all_values = _symbol_averages(
            prefix, start, total_bits, self.samples_per_symbol)
        if all_values is None:
            return None
        all_bits = (all_values > middle).astype(np.uint8)
        data_bits = all_bits[PREAMBLE_BITS + len(SYNC_BITS):]
        data = np.packbits(data_bits, bitorder="big").tobytes()
        body = data[:1 + payload_length]
        received_crc = struct.unpack(">I", data[1 + payload_length:5 + payload_length])[0]
        calculated_crc = zlib.crc32(body) & 0xFFFFFFFF
        if received_crc != calculated_crc:
            return None
        try:
            message = body[1:].decode("utf-8")
        except UnicodeDecodeError:
            return None
        return {
            "status": "SUCCESS",
            "message": message,
            "crc_ok": True,
            "preamble_matches": int(best[0][0]),
            "f0_hz": zero_frequency,
            "f1_hz": one_frequency,
            "estimated_cfo_hz": middle,
            "estimated_deviation_hz": 0.5 * (one_frequency - zero_frequency),
            "sample_start": start,
        }

    def _try_decode(self):
        for edge in self._find_edges(self.buffer):
            result = self._decode_candidate(self.buffer, edge)
            if result is not None:
                return result
        return None

    def _write_result(self, result):
        self.output_text_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_status_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_text_path.write_text(result["message"] + "\n", encoding="utf-8")
        self.output_status_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def work(self, input_items, output_items):
        incoming = np.asarray(input_items[0], dtype=np.complex64)
        if self.result is None and len(incoming):
            self.buffer = np.concatenate((self.buffer, incoming))
            if len(self.buffer) >= 90000 and len(self.buffer) - self.last_attempt_size >= 16384:
                self.last_attempt_size = len(self.buffer)
                result = self._try_decode()
                if result is not None:
                    self.result = result
                    self._write_result(result)
                    print("[SIMPLE RX] SUCCESS, CRC-32 passed")
                    print("[SIMPLE RX] Message:", result["message"])
                    print("[SIMPLE RX] Estimated CFO: %.1f Hz" % result["estimated_cfo_hz"])
            if len(self.buffer) > 400000:
                self.buffer = self.buffer[-250000:]
                self.last_attempt_size = len(self.buffer)
        return len(incoming)

    def stop(self):
        if self.result is None:
            status = {
                "status": "NO_VALID_PACKET",
                "hint": "Check URI, center frequency, gain, attenuation and matching FSK parameters."
            }
            self.output_status_path.parent.mkdir(parents=True, exist_ok=True)
            self.output_status_path.write_text(
                json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print("[SIMPLE RX] No CRC-valid packet found")
        return True
