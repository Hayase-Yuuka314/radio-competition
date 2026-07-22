from pathlib import Path
import json
import sys
import numpy as np
from gnuradio import gr

# GRC evaluates this source before generated-module ``__file__`` exists.
# Support both that parse stage (workspace/demo) and normal runs from demo.
for _CANDIDATE in (
    Path.cwd(), Path.cwd() / "demo",
    Path(r".\demo"),
):
    if (_CANDIDATE / "demo_codec.py").is_file() and str(_CANDIDATE) not in sys.path:
        sys.path.insert(0, str(_CANDIDATE))
from demo_codec import DemoConfig, PROJECT_BACKEND, StreamingDecoder


class blk(gr.sync_block):
    """Streaming burst synchronizer and protected-packet decoder."""

    def __init__(self, shared_key="demo-shared-key-2026", sample_rate=1000000,
                 samples_per_chip=4, code_length=31, team_id=0,
                 expected_sequence=1, output_text_path="decoded_message.txt",
                 output_json_path="rx_status.json"):
        gr.sync_block.__init__(
            self, name="Demo DSSS sync/decoder",
            in_sig=[np.complex64], out_sig=None)
        self.config = DemoConfig(
            sample_rate=int(sample_rate), samples_per_chip=int(samples_per_chip),
            code_length=int(code_length), team_id=int(team_id),
            shared_key=str(shared_key), sequence=int(expected_sequence))
        self.decoder = StreamingDecoder(
            self.config, str(output_text_path), str(output_json_path))
        self.announced = False
        self.output_json_path = Path(str(output_json_path))

    def start(self):
        print("[DEMO RX] Waiting for a protected DSSS packet...")
        print("[DEMO RX] Project codec backend:", PROJECT_BACKEND)
        return True

    def work(self, input_items, output_items):
        result = self.decoder.push(input_items[0])
        if result is not None and not self.announced:
            self.announced = True
            print("[DEMO RX] SUCCESS, CRC-32 passed")
            print("[DEMO RX] Message:", result.message)
            print("[DEMO RX] CFO: %.1f Hz, sync: %.3f, weakest pilot: %.3f" %
                  (result.cfo_hz, result.sync_score, result.minimum_pilot_score))
        return len(input_items[0])

    def stop(self):
        if self.decoder.result is None:
            status = {
                "status": "NO_VALID_PACKET",
                "hint": "Check TX/RX frequency, URI, gain, attenuation and shared parameters.",
                "attempts": self.decoder.attempts,
            }
            self.output_json_path.write_text(
                json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print("[DEMO RX] No CRC-valid packet was found; see rx_status.json")
        return True
