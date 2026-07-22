from pathlib import Path

import numpy as np
from gnuradio import gr


class blk(gr.sync_block):
    """Fail-closed, finite, non-cyclic pyadi-iio Pluto TX sink."""

    def __init__(self, role="sim", rf_enable=False, rules_confirmed=False,
                 physical_path_confirmed=False, rules_path="contest_rules.yaml",
                 device_uri="ip:192.168.2.1", samp_rate=2000000,
                 center_frequency_hz=0, rf_bandwidth_hz=1000000,
                 tx_attenuation_db=-89.75, rf_duration_s=5.0,
                 tx_buffer_samples=32768):
        gr.sync_block.__init__(
            self, name="Contest TX: gated finite Pluto sink",
            in_sig=[np.complex64], out_sig=None)
        self.role = str(role)
        self.rf_enable = bool(rf_enable)
        self.rules_confirmed = bool(rules_confirmed)
        self.physical_path_confirmed = bool(physical_path_confirmed)
        self.rules_path = str(rules_path)
        self.device_uri = str(device_uri)
        self.samp_rate = int(samp_rate)
        self.center_frequency_hz = int(center_frequency_hz)
        self.rf_bandwidth_hz = int(rf_bandwidth_hz)
        self.tx_attenuation_db = float(tx_attenuation_db)
        self.rf_duration_s = float(rf_duration_s)
        self.tx_buffer_samples = int(tx_buffer_samples)
        self._sdr = None
        self._pending = np.empty(0, dtype=np.complex64)
        self._sent = 0
        self._max_samples = 0

    def _validate_rules(self):
        if not (self.rf_enable and self.rules_confirmed and self.physical_path_confirmed):
            raise RuntimeError("RF TX gate closed: enable/rules/physical confirmation required")
        if self.center_frequency_hz <= 0:
            raise RuntimeError("center_frequency_hz is unknown")
        if not (0.0 < self.rf_duration_s <= 3600.0):
            raise RuntimeError("rf_duration_s must be finite and in (0,3600]")
        if not (-89.75 <= self.tx_attenuation_db <= 0.0):
            raise RuntimeError("AD936x tx_attenuation_db must be in [-89.75,0]")
        import yaml
        path = Path(self.rules_path)
        if not path.is_file():
            raise RuntimeError("contest rule file not found")
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not bool((cfg.get("rules") or {}).get("confirmed")):
            raise RuntimeError("contest_rules.yaml rules.confirmed is not true")
        rf = cfg.get("rf") or {}
        centers = rf.get("allowed_center_frequencies_hz")
        bands = rf.get("allowed_bands_hz")
        permitted = False
        if centers:
            permitted = self.center_frequency_hz in [int(v) for v in centers]
        if bands:
            permitted = permitted or any(
                int(lo) <= self.center_frequency_hz <= int(hi) for lo, hi in bands)
        if not permitted:
            raise RuntimeError("center frequency is not explicitly authorized")
        max_bw = rf.get("max_occupied_bandwidth_hz")
        if max_bw is None or self.rf_bandwidth_hz > int(max_bw):
            raise RuntimeError("RF bandwidth is unknown or exceeds constraints")
        duration = (cfg.get("rules") or {}).get("contest_duration_s")
        if duration is None or self.rf_duration_s > float(duration):
            raise RuntimeError("TX duration is unknown or exceeds contest duration")

    def start(self):
        if self.role != "tx":
            return True
        self._validate_rules()
        import adi
        self._sdr = adi.Pluto(uri=self.device_uri)
        self._sdr.sample_rate = self.samp_rate
        self._sdr.tx_lo = self.center_frequency_hz
        self._sdr.tx_rf_bandwidth = self.rf_bandwidth_hz
        self._sdr.tx_hardwaregain_chan0 = self.tx_attenuation_db
        self._sdr.tx_cyclic_buffer = False
        if hasattr(self._sdr, "tx_buffer_size"):
            self._sdr.tx_buffer_size = self.tx_buffer_samples
        self._max_samples = int(self.rf_duration_s * self.samp_rate)
        self._pending = np.empty(0, dtype=np.complex64)
        self._sent = 0
        return True

    def _send(self, samples):
        if not len(samples):
            return
        peak = float(np.max(np.abs(samples)))
        if not np.isfinite(peak):
            raise RuntimeError("TX IQ contains NaN/Inf")
        scaled = np.asarray(samples, dtype=np.complex64)
        if peak > 0.95:
            scaled = scaled * np.float32(0.95 / peak)
        self._sdr.tx(scaled * np.float32(2**14))
        self._sent += len(scaled)

    def work(self, input_items, output_items):
        x = np.asarray(input_items[0], dtype=np.complex64)
        if self.role != "tx":
            return len(x)
        remaining = self._max_samples - self._sent - len(self._pending)
        if remaining <= 0:
            return len(x)
        take = min(len(x), remaining)
        if take:
            self._pending = np.concatenate((self._pending, x[:take]))
        while len(self._pending) >= self.tx_buffer_samples:
            self._send(self._pending[:self.tx_buffer_samples])
            self._pending = self._pending[self.tx_buffer_samples:]
        return len(x)

    def stop(self):
        try:
            if self.role == "tx" and self._sdr is not None and len(self._pending):
                allowed = max(0, self._max_samples - self._sent)
                self._send(self._pending[:allowed])
        finally:
            self._pending = np.empty(0, dtype=np.complex64)
            if self._sdr is not None:
                try:
                    self._sdr.tx_destroy_buffer()
                finally:
                    self._sdr = None
        return True
