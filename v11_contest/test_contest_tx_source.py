import json, sys
from pathlib import Path
import numpy as np
from gnuradio import gr

for _d in (Path.cwd(), Path.cwd()/"v11_contest",
           Path(r"C:\Users\HP\Desktop\radio\radio-competition\v11_contest")):
    if (_d/"contest_codec.py").is_file() and str(_d) not in sys.path:
        sys.path.insert(0, str(_d))
from contest_codec import (ContestConfig, prepare_file_transfer,
                            build_burst, MAX_PAYLOAD_BYTES)

class blk(gr.sync_block):
    def __init__(self, input_path="test_data.txt", sample_rate=1000000,
                 samples_per_chip=4, code_length=127, team_id=0,
                 shared_key="contest-key-2026", amplitude=0.30,
                 gap_samples=50000, hop_enabled=1):
        gr.sync_block.__init__(self, name="Contest TX Source",
                               in_sig=None, out_sig=[np.complex64])
        self.config = ContestConfig(
            sample_rate=int(sample_rate),
            samples_per_chip=int(samples_per_chip),
            code_length=int(code_length), team_id=int(team_id),
            shared_key=str(shared_key), amplitude=float(amplitude),
            gap_samples=int(gap_samples),
            hop_enabled=bool(int(hop_enabled)))
        self.input_path = str(input_path)
        self._waveform = np.empty(0, dtype=np.complex64)
        self._pos = 0
        self._packet_count = 0

    def start(self):
        file_path = Path(self.input_path)
        if not file_path.is_file():
            raise FileNotFoundError(f"not found: {file_path}")
        packets, manifest = prepare_file_transfer(file_path, self.config)
        self._packet_count = len(packets)
        print(f"[TX] file={manifest.file_name} size={manifest.original_size}B"
              f" blocks={manifest.total_blocks} SF={self.config.code_length}"
              f" gain={self.config.processing_gain_db:.1f}dB"
              f" hop={'ON' if self.config.hop_enabled else 'OFF'}")

        # Build repeating waveform: all packets looped
        bursts = []
        for pkt in packets:
            bursts.append(build_burst(pkt, self.config))
        one_cycle = np.concatenate(bursts)
        # Repeat to fill ~5 seconds
        repeats = max(1, int(5.0 * self.config.sample_rate / len(one_cycle)))
        self._waveform = np.tile(one_cycle, repeats).astype(np.complex64)
        self._pos = 0
        print(f"[TX] waveform: {len(one_cycle)} samples/packets "
              f"x{repeats}={len(self._waveform)} total")
        return True

    def work(self, input_items, output_items):
        out = output_items[0]
        n = len(out)
        # Cycle the waveform
        indices = (np.arange(n, dtype=np.int64) + self._pos) % len(self._waveform)
        out[:] = self._waveform[indices]
        self._pos = (self._pos + n) % len(self._waveform)
        return n
