import struct
import zlib
from pathlib import Path
import numpy as np
from gnuradio import gr

class blk(gr.sync_block):
    """读文件→CRC32→组帧→BPSK→RRC→输出IQ"""

    def __init__(self, input_path="test_data.txt",
                 sps=8, alpha=0.35, span=6,
                 preamble_len=64, guard_len=16, seed=42, tx_scale=0.5):
        gr.sync_block.__init__(self, name="TX Source",
                               in_sig=None, out_sig=[np.complex64])
        self.input_path = str(input_path)
        self.sps = int(sps); self.alpha = float(alpha)
        self.span = int(span); self.preamble_len = int(preamble_len)
        self.guard_len = int(guard_len); self.seed = int(seed)
        self.tx_scale = float(tx_scale)
        self.sync_word = 0x1ACF
        self._waveform = np.empty(0, dtype=np.complex64)
        self._cursor = 0

    @staticmethod
    def _rrc(spb, a, sp):
        t = np.arange(-sp, sp + 1e-12, 1.0 / spb)
        pi_t = np.pi * t; f4at = 4.0 * a * t
        denom = pi_t * (1.0 - f4at ** 2)
        numer = np.sin(pi_t * (1.0 - a)) + f4at * np.cos(pi_t * (1.0 + a))
        h = np.zeros_like(t); ok = np.abs(denom) >= 1e-12
        h[ok] = numer[ok] / denom[ok]
        idx0 = np.argmin(np.abs(t))
        h[idx0] = 1.0 - a + 4.0 * a / np.pi
        tsp = 1.0 / (4.0 * a)
        for idx in np.where(np.abs(np.abs(t) - tsp) < 1e-6)[0]:
            h[idx] = (a / np.sqrt(2.0)) * ((1.0 + 2.0 / np.pi) * np.sin(np.pi / (4.0 * a))
                                            + (1.0 - 2.0 / np.pi) * np.cos(np.pi / (4.0 * a)))
        e = np.sum(np.abs(h) ** 2)
        if e > 0: h /= np.sqrt(e)
        return np.float64(h)

    @staticmethod
    def _bpsk(bits):
        return (1.0 - 2.0 * np.asarray(bits, dtype=np.float64)).astype(np.complex128)

    @staticmethod
    def _shape(syms, spb, a, sp):
        rrc = blk._rrc(spb, a, sp)
        up = np.zeros(len(syms) * spb, dtype=np.complex128)
        up[::spb] = syms
        return np.convolve(up, rrc)

    def start(self):
        source = Path(self.input_path)
        if not source.is_file():
            raise FileNotFoundError(f"input not found: {source}")
        data = source.read_bytes()
        crc = zlib.crc32(data) & 0xFFFFFFFF
        payload_crc = data + struct.pack(">I", crc)
        payload_bits = np.unpackbits(np.frombuffer(payload_crc, dtype=np.uint8))
        len_bits = np.unpackbits(np.array([len(data)], dtype=">u2").view(np.uint8))
        sync_bits = np.unpackbits(np.array([self.sync_word], dtype=">u2").view(np.uint8))
        guard_syms = np.zeros(self.guard_len, dtype=np.complex128)
        rng = np.random.default_rng(self.seed)
        pream_bits = (rng.random(self.preamble_len) > 0.5).astype(np.uint8)
        pream_syms = self._bpsk(pream_bits)
        syms = np.concatenate([
            guard_syms, pream_syms,
            self._bpsk(sync_bits), self._bpsk(len_bits),
            self._bpsk(payload_bits), guard_syms])
        iq = self._shape(syms, self.sps, self.alpha, self.span)
        peak = float(np.max(np.abs(iq)))
        if peak > 0: iq = iq * np.float32(self.tx_scale / peak)
        self._waveform = np.asarray(iq, dtype=np.complex64)
        self._cursor = 0
        print(f"[TX] file={source.name} size={len(data)}B IQ={len(self._waveform)}")
        return True

    def work(self, input_items, output_items):
        if self._cursor >= len(self._waveform): return -1
        out = output_items[0]
        n = min(len(out), len(self._waveform) - self._cursor)
        out[:n] = self._waveform[self._cursor:self._cursor + n]
        self._cursor += n
        return n
