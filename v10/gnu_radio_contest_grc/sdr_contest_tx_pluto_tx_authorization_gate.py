from pathlib import Path

import numpy as np
import yaml
from gnuradio import gr


def validate_tx_configuration(rf_enable=False, rules_confirmed=False,
                              physical_path_confirmed=False,
                              rules_path="contest_rules.yaml",
                              center_frequency_hz=2400000000,
                              rf_bandwidth_hz=1000000,
                              rf_duration_s=5.0,
                              tx_attenuation_db=89.75):
    """Validate before the native Pluto sink is constructed or scheduled."""
    if not (bool(rf_enable) and bool(rules_confirmed) and
            bool(physical_path_confirmed)):
        raise RuntimeError(
            "RF TX gate closed: rf_enable, rules_confirmed and "
            "physical_path_confirmed must all be true")
    center_frequency_hz = int(center_frequency_hz)
    rf_bandwidth_hz = int(rf_bandwidth_hz)
    rf_duration_s = float(rf_duration_s)
    tx_attenuation_db = float(tx_attenuation_db)
    if center_frequency_hz <= 0:
        raise RuntimeError("center_frequency_hz must be explicitly set")
    if not (0.0 < rf_duration_s <= 3600.0):
        raise RuntimeError("rf_duration_s must be finite and in (0, 3600]")
    if not (0.0 <= tx_attenuation_db <= 89.75):
        raise RuntimeError("Pluto attenuation must be in [0, 89.75] dB")

    path = Path(str(rules_path))
    if not path.is_file():
        raise RuntimeError("contest rule file not found: %s" % path)
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rules = cfg.get("rules") or {}
    rf = cfg.get("rf") or {}
    if not bool(rules.get("confirmed")):
        raise RuntimeError("contest_rules.yaml rules.confirmed is not true")

    centers = [int(value) for value in
               (rf.get("allowed_center_frequencies_hz") or [])]
    bands = rf.get("allowed_bands_hz") or []
    permitted = center_frequency_hz in centers
    permitted = permitted or any(
        int(low) <= center_frequency_hz <= int(high)
        for low, high in bands)
    if not permitted:
        raise RuntimeError("center frequency is not explicitly authorized")

    max_bw = rf.get("max_occupied_bandwidth_hz")
    if max_bw is None or rf_bandwidth_hz > int(max_bw):
        raise RuntimeError("RF bandwidth is unknown or exceeds constraints")
    max_duration = rules.get("contest_duration_s")
    if max_duration is None or rf_duration_s > float(max_duration):
        raise RuntimeError("TX duration is unknown or exceeds contest duration")
    return True


class blk(gr.sync_block):
    """Fail-closed contest-rule gate placed immediately before PlutoSDR Sink."""

    def __init__(self, rf_enable=False, rules_confirmed=False,
                 physical_path_confirmed=False,
                 rules_path="contest_rules.yaml",
                 center_frequency_hz=2400000000,
                 rf_bandwidth_hz=1000000,
                 rf_duration_s=5.0,
                 tx_attenuation_db=89.75):
        gr.sync_block.__init__(
            self, name="TX authorization gate (fail closed)",
            in_sig=[np.complex64], out_sig=[np.complex64])
        self.rf_enable = bool(rf_enable)
        self.rules_confirmed = bool(rules_confirmed)
        self.physical_path_confirmed = bool(physical_path_confirmed)
        self.rules_path = str(rules_path)
        self.center_frequency_hz = int(center_frequency_hz)
        self.rf_bandwidth_hz = int(rf_bandwidth_hz)
        self.rf_duration_s = float(rf_duration_s)
        self.tx_attenuation_db = float(tx_attenuation_db)

    def start(self):
        return validate_tx_configuration(
            rf_enable=self.rf_enable,
            rules_confirmed=self.rules_confirmed,
            physical_path_confirmed=self.physical_path_confirmed,
            rules_path=self.rules_path,
            center_frequency_hz=self.center_frequency_hz,
            rf_bandwidth_hz=self.rf_bandwidth_hz,
            rf_duration_s=self.rf_duration_s,
            tx_attenuation_db=self.tx_attenuation_db,
        )

    def work(self, input_items, output_items):
        source = input_items[0]
        output_items[0][:len(source)] = source
        return len(source)
