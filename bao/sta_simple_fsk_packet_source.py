import struct
import zlib
import numpy as np
from gnuradio import gr

PREAMBLE_BITS = 64
SYNC_BYTES = bytes.fromhex("DDAA55D3")
MAX_PAYLOAD_BYTES = 64


def _bytes_to_bits(data):
    return np.unpackbits(np.frombuffer(data, dtype=np.uint8), bitorder="big")


class blk(gr.sync_block):
    """Repeating 2-FSK packet source with preamble, length and CRC-32."""

    def __init__(self, message="el psy kongroo", sample_rate=1000000,
                 samples_per_symbol=100, deviation_hz=75000.0,
                 amplitude=0.25, gap_samples=20000):
        gr.sync_block.__init__(
            self, name="Simple 2-FSK text packet source",
            in_sig=None, out_sig=[np.complex64])
        payload = str(message).encode("utf-8")
        if len(payload) > MAX_PAYLOAD_BYTES:
            raise ValueError("message is longer than 64 UTF-8 bytes")
        self.sample_rate = int(sample_rate)
        self.samples_per_symbol = int(samples_per_symbol)
        self.deviation_hz = float(deviation_hz)
        self.amplitude = float(amplitude)
        self.gap_samples = int(gap_samples)
        if self.samples_per_symbol < 8:
            raise ValueError("samples_per_symbol must be at least 8")
        if not (0.01 <= self.amplitude <= 0.8):
            raise ValueError("amplitude must be between 0.01 and 0.8")

        preamble = (np.arange(PREAMBLE_BITS, dtype=np.uint8) & 1)
        body = bytes((len(payload),)) + payload
        crc = struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        bits = np.concatenate((
            preamble,
            _bytes_to_bits(SYNC_BYTES),
            _bytes_to_bits(body + crc),
        )).astype(np.uint8)

        symbol_frequencies = np.where(
            bits == 0, -self.deviation_hz, self.deviation_hz)
        sample_frequencies = np.repeat(
            symbol_frequencies, self.samples_per_symbol)
        phase_increment = 2.0 * np.pi * sample_frequencies / self.sample_rate
        active = self.amplitude * np.exp(1j * np.cumsum(phase_increment))
        gap = np.zeros(self.gap_samples, dtype=np.complex64)
        self.waveform = np.concatenate((gap, active.astype(np.complex64)))
        self.position = 0
        self.message = str(message)
        self.packet_bits = len(bits)

    def start(self):
        print("[SIMPLE TX] Message:", self.message)
        print("[SIMPLE TX] 2-FSK packet bits:", self.packet_bits,
              "cycle samples:", len(self.waveform))
        return True

    def work(self, input_items, output_items):
        output = output_items[0]
        count = len(output)
        indices = (np.arange(count, dtype=np.int64) + self.position) % len(self.waveform)
        output[:] = self.waveform[indices]
        self.position = int((self.position + count) % len(self.waveform))
        return count
