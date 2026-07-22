import numpy as np
from gnuradio import gr

class blk(gr.sync_block):
    """PlutoSDR TX: 将IQ流发送到PlutoSDR"""

    def __init__(self, device_uri="ip:192.168.2.1",
                 samp_rate=2000000, center_freq=2450000000,
                 rf_bandwidth=1000000, tx_gain=-10.0, tx_scale=0.5):
        gr.sync_block.__init__(self, name="Pluto TX Sink",
                               in_sig=[np.complex64], out_sig=None)
        self.device_uri = str(device_uri)
        self.samp_rate = int(samp_rate)
        self.center_freq = int(center_freq)
        self.rf_bandwidth = int(rf_bandwidth)
        self.tx_gain = float(tx_gain)
        self.tx_scale = float(tx_scale)
        self._sdr = None

    def start(self):
        import adi
        self._sdr = adi.Pluto(uri=self.device_uri)
        self._sdr.sample_rate = self.samp_rate
        self._sdr.tx_lo = self.center_freq
        self._sdr.tx_rf_bandwidth = self.rf_bandwidth
        self._sdr.tx_hardwaregain_chan0 = self.tx_gain
        self._sdr.tx_cyclic_buffer = False
        print(f"[TX Pluto] uri={self.device_uri} freq={self.center_freq} "
              f"rate={self.samp_rate} gain={self.tx_gain}dB")

        # warm-up: 发送一小段静默避免初始毛刺
        self._sdr.tx(np.zeros(1024, dtype=np.complex64) * np.float32(2**14))
        return True

    def work(self, input_items, output_items):
        x = np.asarray(input_items[0], dtype=np.complex64)
        if len(x):
            peak = float(np.max(np.abs(x)))
            if peak > self.tx_scale:
                x = x * (self.tx_scale / peak)
            self._sdr.tx(x * np.float32(2**14))  # AD936x expects 12-bit scaled IQ
        return len(x)

    def stop(self):
        if self._sdr is not None:
            self._sdr.tx_destroy_buffer()
            self._sdr = None
            print("[TX Pluto] buffer destroyed, device released")
        return True
