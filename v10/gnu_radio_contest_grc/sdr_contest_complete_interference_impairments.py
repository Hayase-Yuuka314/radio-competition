import numpy as np
from gnuradio import gr


class blk(gr.sync_block):
    """Stateful tone/burst interference, IQ imbalance, DC and clipping."""

    def __init__(self, role="sim", samp_rate=2000000, reference_amplitude=0.5,
                 tone_inr_db=-120.0, tone_offset_hz=100000.0,
                 burst_probability=0.0, burst_inr_db=10.0,
                 clipping_threshold=0.95, iq_gain_db=0.0,
                 iq_phase_deg=0.0, dc_real=0.0, dc_imag=0.0, seed=42):
        gr.sync_block.__init__(
            self, name="Contest Channel: interference/IQ/clipping",
            in_sig=[np.complex64], out_sig=[np.complex64])
        self.role = str(role)
        self.samp_rate = float(samp_rate)
        self.reference_amplitude = float(reference_amplitude)
        self.tone_inr_db = float(tone_inr_db)
        self.tone_offset_hz = float(tone_offset_hz)
        self.burst_probability = float(burst_probability)
        self.burst_inr_db = float(burst_inr_db)
        self.clipping_threshold = float(clipping_threshold)
        self.iq_gain_db = float(iq_gain_db)
        self.iq_phase_deg = float(iq_phase_deg)
        self.dc_real = float(dc_real)
        self.dc_imag = float(dc_imag)
        self.seed = int(seed)
        self._rng = np.random.default_rng(self.seed)
        self._sample_index = 0

    def start(self):
        if not (0.0 <= self.burst_probability <= 1.0):
            raise ValueError("burst_probability must be in [0,1]")
        if self.samp_rate <= 0:
            raise ValueError("samp_rate must be positive")
        self._rng = np.random.default_rng(self.seed)
        self._sample_index = 0
        return True

    def work(self, input_items, output_items):
        x = np.asarray(input_items[0], dtype=np.complex64)
        y = x.astype(np.complex128, copy=True)
        n = len(y)
        if self.role == "sim" and n:
            if self.tone_inr_db > -100.0:
                idx = self._sample_index + np.arange(n, dtype=np.float64)
                amp = self.reference_amplitude * 10.0 ** (self.tone_inr_db / 20.0)
                y += amp * np.exp(1j * 2.0 * np.pi * self.tone_offset_hz * idx / self.samp_rate)
            if self.burst_probability > 0.0:
                mask = self._rng.random(n) < self.burst_probability
                count = int(np.count_nonzero(mask))
                if count:
                    amp = self.reference_amplitude * 10.0 ** (self.burst_inr_db / 20.0)
                    noise = (self._rng.standard_normal(count) +
                             1j * self._rng.standard_normal(count)) / np.sqrt(2.0)
                    y[mask] += amp * noise
            if self.iq_gain_db != 0.0 or self.iq_phase_deg != 0.0:
                gain = 10.0 ** (self.iq_gain_db / 20.0)
                phase = np.deg2rad(self.iq_phase_deg)
                i = np.real(y) * gain
                q = np.imag(y) / max(gain, 1e-12)
                y = (i * np.cos(phase) - q * np.sin(phase) +
                     1j * (i * np.sin(phase) + q * np.cos(phase)))
            y += complex(self.dc_real, self.dc_imag)
            if self.clipping_threshold > 0.0:
                mag = np.abs(y)
                over = mag > self.clipping_threshold
                y[over] *= self.clipping_threshold / mag[over]
        output_items[0][:n] = y.astype(np.complex64)
        self._sample_index += n
        return n
