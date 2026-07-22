from pathlib import Path
import json
import sys
import numpy as np
from gnuradio import gr

# GRC evaluates this source before generated-module ``__file__`` exists.
# Support both that parse stage (workspace/demo) and normal runs from demo.
for _CANDIDATE in (
    Path.cwd(), Path.cwd() / "demo",
    Path(r"C:\Users\HP\Desktop\demo\demo"),
):
    if (_CANDIDATE / "demo_codec.py").is_file() and str(_CANDIDATE) not in sys.path:
        sys.path.insert(0, str(_CANDIDATE))
from demo_codec import DemoConfig, build_repeating_waveform


class blk(gr.sync_block):
    """Infinite, repeating source containing one complete protected text packet."""

    def __init__(self, message="el psy kongroo", shared_key="demo-shared-key-2026",
                 sample_rate=1000000, samples_per_chip=4, code_length=31,
                 team_id=0, amplitude=0.25, gap_samples=25000, sequence=1,
                 manifest_path="tx_manifest.json"):
        gr.sync_block.__init__(
            self, name="Demo packet FEC/interleave/DSSS",
            in_sig=None, out_sig=[np.complex64])
        self.config = DemoConfig(
            sample_rate=int(sample_rate), samples_per_chip=int(samples_per_chip),
            code_length=int(code_length), team_id=int(team_id),
            shared_key=str(shared_key), amplitude=float(amplitude),
            gap_samples=int(gap_samples), sequence=int(sequence))
        self.waveform, metadata = build_repeating_waveform(str(message), self.config)
        Path(str(manifest_path)).write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.position = 0
        self.metadata = metadata

    def start(self):
        print("[DEMO TX] Repeating protected message:", self.metadata["payload_utf8"])
        print("[DEMO TX] Cycle samples:", self.metadata["cycle_samples"],
              "processing gain: %.1f dB" % self.metadata["processing_gain_db"])
        return True

    def work(self, input_items, output_items):
        output = output_items[0]
        count = len(output)
        indices = (np.arange(count, dtype=np.int64) + self.position) % len(self.waveform)
        output[:] = self.waveform[indices]
        self.position = int((self.position + count) % len(self.waveform))
        return count
