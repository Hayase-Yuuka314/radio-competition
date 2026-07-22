"""Offline acceptance test for the PlutoSDR TX/RX demo.

This does not open RF hardware.  It checks the exact packet encoder/decoder used
by the two .grc files, including CFO, noise, a continuous narrow-band interferer,
sample-clock error, shared-key protection and CRC rejection.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys
import tempfile

import numpy as np

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from demo_codec import (  # noqa: E402
    DemoConfig,
    PROJECT_BACKEND,
    StreamingDecoder,
    build_repeating_waveform,
    decode_capture,
    simulate_channel,
)


def resample_clock_error(samples: np.ndarray, ppm: float) -> np.ndarray:
    scale = 1.0 + float(ppm) * 1e-6
    source_positions = np.arange(int(len(samples) * scale), dtype=np.float64) / scale
    original_positions = np.arange(len(samples), dtype=np.float64)
    real = np.interp(source_positions, original_positions, np.real(samples))
    imag = np.interp(source_positions, original_positions, np.imag(samples))
    return (real + 1j * imag).astype(np.complex64)


def validate_grc_files() -> None:
    try:
        import yaml
    except ImportError:
        print("[SKIP] PyYAML unavailable; GRC YAML structure was not re-read")
        return
    for filename in ("demo_tx_pluto.grc", "demo_rx_pluto.grc"):
        path = HERE / filename
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert document["metadata"]["file_format"] == 1
        assert document["connections"]
        for block in document["blocks"]:
            if block.get("id") == "epy_block":
                ast.parse(block["parameters"]["_source_code"])
        print(f"[OK] {filename}: YAML and Embedded Python syntax")


def main() -> int:
    message = "el psy kongroo"
    config = DemoConfig()
    waveform, metadata = build_repeating_waveform(message, config)
    assert len(waveform) == config.cycle_samples
    print("[OK] TX waveform built")
    print(
        "     cycle=%d samples, DSSS gain=%.1f dB, project_backend=%s"
        % (len(waveform), metadata["processing_gain_db"], PROJECT_BACKEND)
    )

    capture = simulate_channel(
        waveform,
        config,
        repetitions=3,
        cfo_hz=18_000.0,
        snr_db=5.0,
        tone_interference_amplitude=0.08,
    )
    capture = resample_clock_error(capture, ppm=100.0)
    result = decode_capture(capture, config)
    assert result is not None, "decoder did not find a valid packet"
    assert result.message == message
    assert result.crc_ok
    print("[OK] RX recovered exact UTF-8 message through impaired channel")
    print(
        "     message=%r, CFO=%.1f Hz, sync=%.3f, weakest_pilot=%.3f"
        % (result.message, result.cfo_hz, result.sync_score, result.minimum_pilot_score)
    )

    wrong_key = DemoConfig(shared_key="definitely-the-wrong-key")
    assert decode_capture(capture, wrong_key) is None
    print("[OK] Wrong shared key is rejected by CRC-32")

    with tempfile.TemporaryDirectory(prefix="dsss_demo_") as directory:
        output_text = Path(directory) / "decoded_message.txt"
        output_json = Path(directory) / "rx_status.json"
        streaming = StreamingDecoder(config, str(output_text), str(output_json))
        chunk = 8192
        for first in range(0, len(capture), chunk):
            streaming.push(capture[first : first + chunk])
            if streaming.result is not None:
                break
        assert streaming.result is not None
        assert output_text.read_text(encoding="utf-8").strip() == message
        assert '"status": "SUCCESS"' in output_json.read_text(encoding="utf-8")
    print("[OK] GNU Radio-style streaming chunks and output files")

    validate_grc_files()
    print("\nALL OFFLINE DEMO TESTS PASSED")
    print("Hardware RF validation still requires GNU Radio, gr-iio and a connected PlutoSDR.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

