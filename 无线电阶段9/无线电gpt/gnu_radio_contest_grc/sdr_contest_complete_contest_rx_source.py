import json
import os
from pathlib import Path

import numpy as np
from gnuradio import gr


class blk(gr.sync_block):
    """Bounded replay or RX-only Pluto/NanoSDR source."""

    def __init__(self, role="sim", replay_path="rx_capture.c64",
                 device_uri="ip:192.168.2.1", samp_rate=2000000,
                 center_frequency_hz=0, rf_bandwidth_hz=1000000,
                 rx_gain_mode="manual", rx_gain_db=30.0,
                 rx_buffer_samples=32768, rf_duration_s=5.0,
                 max_capture_samples=10000000,
                 device_manifest_path="rx_device_manifest.json"):
        gr.sync_block.__init__(
            self, name="Contest RX: bounded IQ replay/Pluto",
            in_sig=None, out_sig=[np.complex64])
        self.role = str(role)
        self.replay_path = str(replay_path)
        self.device_uri = str(device_uri)
        self.samp_rate = int(samp_rate)
        self.center_frequency_hz = int(center_frequency_hz)
        self.rf_bandwidth_hz = int(rf_bandwidth_hz)
        self.rx_gain_mode = str(rx_gain_mode)
        self.rx_gain_db = float(rx_gain_db)
        self.rx_buffer_samples = int(rx_buffer_samples)
        self.rf_duration_s = float(rf_duration_s)
        self.max_capture_samples = int(max_capture_samples)
        self.device_manifest_path = str(device_manifest_path)
        self._data = np.empty(0, dtype=np.complex64)
        self._pending = np.empty(0, dtype=np.complex64)
        self._cursor = 0
        self._remaining = 0
        self._sdr = None

    def _write_manifest(self, payload):
        target = Path(self.device_manifest_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        os.replace(tmp, target)

    def start(self):
        if self.role == "replay":
            path = Path(self.replay_path)
            if not path.is_file():
                raise FileNotFoundError("IQ replay file not found: %s" % path)
            count = min(path.stat().st_size // 8, self.max_capture_samples)
            self._data = np.fromfile(path, dtype=np.complex64, count=count)
            self._cursor = 0
            self._write_manifest({
                "mode": "replay", "path": str(path.resolve()),
                "datatype": "cf32_le", "sample_rate_hz": self.samp_rate,
                "samples": int(len(self._data)),
                "center_frequency_hz": self.center_frequency_hz})
            return True
        if self.role != "rx":
            return True
        if self.center_frequency_hz <= 0:
            raise ValueError("RX center_frequency_hz must be explicitly set")
        if not (0.0 < self.rf_duration_s <= 3600.0):
            raise ValueError("rf_duration_s must be finite and in (0,3600]")
        requested = int(self.rf_duration_s * self.samp_rate)
        self._remaining = min(requested, self.max_capture_samples)
        import adi
        self._sdr = adi.Pluto(uri=self.device_uri)
        self._sdr.sample_rate = self.samp_rate
        self._sdr.rx_lo = self.center_frequency_hz
        self._sdr.rx_rf_bandwidth = self.rf_bandwidth_hz
        self._sdr.gain_control_mode_chan0 = self.rx_gain_mode
        if self.rx_gain_mode == "manual":
            self._sdr.rx_hardwaregain_chan0 = self.rx_gain_db
        self._sdr.rx_buffer_size = self.rx_buffer_samples
        self._write_manifest({
            "mode": "rx", "uri": self.device_uri, "datatype": "cf32_le",
            "sample_rate_hz_requested": self.samp_rate,
            "sample_rate_hz_readback": int(self._sdr.sample_rate),
            "center_frequency_hz_requested": self.center_frequency_hz,
            "center_frequency_hz_readback": int(self._sdr.rx_lo),
            "rf_bandwidth_hz_requested": self.rf_bandwidth_hz,
            "rf_bandwidth_hz_readback": int(self._sdr.rx_rf_bandwidth),
            "gain_mode": self.rx_gain_mode,
            "manual_gain_db": self.rx_gain_db if self.rx_gain_mode == "manual" else None,
            "duration_s": self.rf_duration_s,
            "max_samples": self._remaining})
        return True

    def work(self, input_items, output_items):
        out = output_items[0]
        if self.role == "replay":
            if self._cursor >= len(self._data):
                return -1
            n = min(len(out), len(self._data) - self._cursor)
            out[:n] = self._data[self._cursor:self._cursor + n]
            self._cursor += n
            return n
        if self.role != "rx" or self._remaining <= 0:
            return -1
        produced = 0
        while produced < len(out) and self._remaining > 0:
            if not len(self._pending):
                self._pending = np.asarray(self._sdr.rx(), dtype=np.complex64).reshape(-1)
            n = min(len(out) - produced, len(self._pending), self._remaining)
            out[produced:produced + n] = self._pending[:n]
            self._pending = self._pending[n:]
            produced += n
            self._remaining -= n
        return produced if produced else -1

    def stop(self):
        self._pending = np.empty(0, dtype=np.complex64)
        self._sdr = None
        return True
