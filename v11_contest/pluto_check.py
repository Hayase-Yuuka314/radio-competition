"""Pluto loopback check — TX tone -> RX detect"""
import adi, numpy as np, time

URI  = "usb:1.5.5"
FREQ = 2440000000

sdr = adi.Pluto(uri=URI)
sdr.sample_rate = 1_000_000
sdr.tx_lo = FREQ; sdr.rx_lo = FREQ
sdr.tx_rf_bandwidth = 1_000_000; sdr.rx_rf_bandwidth = 1_000_000
sdr.tx_hardwaregain_chan0 = 0
sdr.gain_control_mode_chan0 = "manual"
sdr.rx_hardwaregain_chan0 = 10
sdr.tx_cyclic_buffer = False

tone = np.exp(1j*2*np.pi*100e3*np.arange(50000)/1e6).astype(np.complex64)*0.5
sdr.tx(tone)
time.sleep(0.1)
rx = np.asarray(sdr.rx()).ravel()

pwr_tx   = 10*np.log10(np.mean(np.abs(tone)**2)+1e-20)
pwr_rx   = 10*np.log10(np.mean(np.abs(rx)**2)+1e-20)
pwr_noise = 10*np.log10(np.mean(np.abs(rx[:10000])**2)+1e-20)
print(f"TX: {pwr_tx:.1f}dB  RX: {pwr_rx:.1f}dB  noise: {pwr_noise:.1f}dB")
print("LOOPBACK OK" if pwr_rx - pwr_noise > 5 else "LOOPBACK FAIL")
sdr.tx_destroy_buffer()
