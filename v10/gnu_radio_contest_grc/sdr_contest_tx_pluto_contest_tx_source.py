import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pmt
from gnuradio import gr


class blk(gr.sync_block):
    """Finite file-to-IQ source using the repository's tested PHY protocol."""

    def __init__(self, role="sim", input_path="input_payload.bin",
                 manifest_path="tx_manifest.json", modulation="bpsk",
                 fec_mode="convolutional", samp_rate=2000000,
                 samples_per_symbol=8, rolloff=0.35, span=6,
                 block_size=256, preamble_symbols=64, guard_symbols=16,
                 seed=42, tx_scale=0.5):
        gr.sync_block.__init__(
            self, name="Contest TX: file/framing/FEC/mod/RRC",
            in_sig=None, out_sig=[np.complex64])
        self.role = str(role)
        self.input_path = str(input_path)
        self.manifest_path = str(manifest_path)
        self.modulation = str(modulation).lower()
        self.fec_mode = str(fec_mode).lower()
        self.samp_rate = int(samp_rate)
        self.samples_per_symbol = int(samples_per_symbol)
        self.rolloff = float(rolloff)
        self.span = int(span)
        self.block_size = int(block_size)
        self.preamble_symbols = int(preamble_symbols)
        self.guard_symbols = int(guard_symbols)
        self.seed = int(seed)
        self.tx_scale = float(tx_scale)
        self._waveform = np.empty(0, dtype=np.complex64)
        self._frames = []
        self._frame_offsets = []
        self._cursor = 0
        self._next_tag = 0

    @staticmethod
    def _atomic_json(path, payload):
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        os.replace(tmp, target)

    def start(self):
        if self.role not in ("sim", "tx"):
            return True
        if self.preamble_symbols != 64:
            raise ValueError("protocol v1 requires preamble_symbols=64")
        if self.guard_symbols < 1 or self.samples_per_symbol < 2:
            raise ValueError("guard_symbols and samples_per_symbol are invalid")
        if not (0.0 < self.tx_scale <= 0.95):
            raise ValueError("tx_scale must be in (0, 0.95]")

        from wireless_competition.common.types import FECType, ModulationType
        from wireless_competition.tx.pipeline import TXPipeline

        mod_map = {"bpsk": ModulationType.BPSK, "qpsk": ModulationType.QPSK}
        fec_map = {"none": FECType.NONE, "convolutional": FECType.CONVOLUTIONAL}
        if self.modulation not in mod_map:
            raise ValueError("modulation must be bpsk or qpsk")
        if self.fec_mode not in fec_map:
            raise ValueError("fec_mode must be none or convolutional")

        source = Path(self.input_path)
        if not source.is_file():
            raise FileNotFoundError("input payload not found: %s" % source)
        data = source.read_bytes()
        tx = TXPipeline(
            modulation=mod_map[self.modulation], fec_type=fec_map[self.fec_mode],
            samples_per_symbol=self.samples_per_symbol, rolloff=self.rolloff,
            span=self.span, block_size=self.block_size,
            preamble_length_symbols=self.preamble_symbols,
            guard_length_symbols=self.guard_symbols, seed=self.seed)
        raw_frames = tx.process_file(data)
        self._frames = []
        for frame in raw_frames:
            frame = np.asarray(frame, dtype=np.complex64)
            peak = float(np.max(np.abs(frame))) if frame.size else 0.0
            if peak > 0.0:
                frame = frame * np.float32(self.tx_scale / peak)
            self._frames.append(frame.astype(np.complex64, copy=False))
        self._frame_offsets = []
        offset = 0
        for frame in self._frames:
            self._frame_offsets.append((offset, len(frame)))
            offset += len(frame)
        self._waveform = (np.concatenate(self._frames)
                          if self._frames else np.empty(0, dtype=np.complex64))
        self._cursor = 0
        self._next_tag = 0
        manifest = {
            "protocol_version": 1,
            "input_path": str(source.resolve()),
            "payload_bytes": len(data),
            "payload_sha256": hashlib.sha256(data).hexdigest(),
            "frame_count": len(self._frames),
            "frame_lengths_samples": [len(f) for f in self._frames],
            "sample_rate_hz": self.samp_rate,
            "modulation": self.modulation,
            "fec": self.fec_mode,
            "block_size_bytes": self.block_size,
            "samples_per_symbol": self.samples_per_symbol,
            "rrc_rolloff": self.rolloff,
            "rrc_span": self.span,
            "preamble_symbols": self.preamble_symbols,
            "guard_symbols": self.guard_symbols,
            "seed": self.seed,
            "peak_scale": self.tx_scale,
        }
        self._atomic_json(self.manifest_path, manifest)
        return True

    def work(self, input_items, output_items):
        if self._cursor >= len(self._waveform):
            return -1
        out = output_items[0]
        count = min(len(out), len(self._waveform) - self._cursor)
        absolute_start = int(self.nitems_written(0))
        absolute_end = absolute_start + count
        while self._next_tag < len(self._frame_offsets):
            tag_offset, frame_len = self._frame_offsets[self._next_tag]
            if tag_offset >= absolute_end:
                break
            if tag_offset >= absolute_start:
                self.add_item_tag(0, int(tag_offset), pmt.intern("frame_len"),
                                  pmt.from_long(int(frame_len)))
            self._next_tag += 1
        out[:count] = self._waveform[self._cursor:self._cursor + count]
        self._cursor += count
        return count
