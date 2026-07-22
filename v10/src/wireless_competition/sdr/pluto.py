"""PlutoSDR / NanoSDR hardware driver.

Wraps the ADALM-Pluto (PlutoSDR) via libiio / pyadi-iio for real
over-the-air transmission and reception. Falls back to simulated
mode when hardware is unavailable.

Hardware constraints (competition):
- TX SDR: PlutoSDR TX → 2.4GHz BPF → antenna
- RX SDR: antenna → PlutoSDR RX (no external filter)
- TDD ensures TX and RX never operate simultaneously
- RX SDR gain is reduced during TX slots for protection
"""

from __future__ import annotations

import math
import time
from typing import Optional

import numpy as np

from ..common.types import DeviceHealth, RxHardwareConfig, TxHardwareConfig
from .base import SDRDevice

_adi_available = False
_adi_error = "pyadi-iio not installed"

try:
    import adi  # type: ignore
    _adi_available = True
    _adi_error = ""
except ImportError:
    pass

try:
    import iio  # type: ignore
    _IIO_AVAILABLE = True
except ImportError:
    _IIO_AVAILABLE = False


class PlutoSDRDevice(SDRDevice):
    """PlutoSDR / ADALM-PLUTO hardware interface.

    Supports both real hardware and simulated fallback for development.

    Hardware mode (pyadi-iio available):
        device = PlutoSDRDevice(uri="ip:192.168.2.1")

    Simulation mode (no hardware):
        device = PlutoSDRDevice(uri="simulated://")

    Usage:
        device = PlutoSDRDevice(uri="ip:192.168.2.1", sample_rate_hz=2e6)
        device.configure_tx(TxHardwareConfig(center_frequency_hz=2.45e9))
        device.transmit(iq_samples)

        rx_device = PlutoSDRDevice(uri="ip:192.168.2.1", sample_rate_hz=2e6)
        rx_device.configure_rx(RxHardwareConfig(center_frequency_hz=2.45e9))
        data = rx_device.receive(32768)
    """

    def __init__(
        self,
        uri: str = "ip:192.168.2.1",
        sample_rate_hz: float = 2.0e6,
        force_sim: bool = False,
    ):
        self._uri = uri
        self._sample_rate_hz = sample_rate_hz
        self._force_sim = force_sim
        self._initialized = False

        self._sdr: Optional[adi.Pluto] = None
        self._rx_config: Optional[RxHardwareConfig] = None
        self._tx_config: Optional[TxHardwareConfig] = None

        self._is_simulation = force_sim or not _adi_available
        self._sim_rx_buffer: np.ndarray = np.array([], dtype=np.complex64)

        self._tx_sample_count: int = 0
        self._rx_sample_count: int = 0
        self._dropped_samples: int = 0
        self._last_error: str = ""

        if _adi_available and not force_sim:
            self._init_hardware()

    def _init_hardware(self):
        """Initialize real PlutoSDR hardware."""
        try:
            self._sdr = adi.Pluto(self._uri)
            self._initialized = True
        except Exception as e:
            self._last_error = str(e)
            self._is_simulation = True
            self._sdr = None

    def configure_rx(self, config: RxHardwareConfig) -> None:
        self._rx_config = config
        self._sample_rate_hz = config.sample_rate_hz

        if self._is_simulation or self._sdr is None:
            return

        try:
            self._sdr.rx_lo = int(config.center_frequency_hz)
            self._sdr.sample_rate = int(config.sample_rate_hz)
            self._sdr.rx_rf_bandwidth = int(config.rf_bandwidth_hz)
            self._sdr.rx_buffer_size = config.buffer_size_samples

            if config.gain_mode == "manual":
                self._sdr.gain_control_mode_chan0 = "manual"
                try:
                    self._sdr.rx_hardwaregain_chan0 = config.gain_db
                except Exception:
                    pass
            else:
                self._sdr.gain_control_mode_chan0 = config.gain_mode
        except Exception as e:
            self._last_error = f"RX config error: {e}"

    def configure_tx(self, config: TxHardwareConfig) -> None:
        self._tx_config = config
        self._sample_rate_hz = config.sample_rate_hz

        if self._is_simulation or self._sdr is None:
            return

        try:
            self._sdr.tx_lo = int(config.center_frequency_hz)
            self._sdr.sample_rate = int(config.sample_rate_hz)
            self._sdr.tx_rf_bandwidth = int(config.rf_bandwidth_hz)

            try:
                self._sdr.tx_hardwaregain_chan0 = -config.attenuation_db
            except Exception:
                pass
        except Exception as e:
            self._last_error = f"TX config error: {e}"

    def receive(self, num_samples: int) -> np.ndarray:
        """Receive IQ samples from SDR.

        For real hardware: blocks until num_samples are available.
        For simulation: returns from internal buffer (0-fill if empty).
        """
        if num_samples <= 0:
            return np.array([], dtype=np.complex64)

        if self._is_simulation or self._sdr is None:
            return self._sim_receive(num_samples)

        try:
            data = self._sdr.rx()
            if data is None or len(data) == 0:
                self._dropped_samples += num_samples
                return np.zeros(num_samples, dtype=np.complex64)

            self._rx_sample_count += len(data)
            result = np.asarray(data, dtype=np.complex64).flatten()

            result = result[:num_samples]
            if len(result) < num_samples:
                pad = np.zeros(num_samples - len(result), dtype=np.complex64)
                result = np.concatenate([result, pad])

            return result
        except Exception as e:
            self._last_error = f"RX error: {e}"
            self._dropped_samples += num_samples
            return np.zeros(num_samples, dtype=np.complex64)

    def transmit(self, iq: np.ndarray) -> None:
        """Transmit IQ samples via SDR.

        For simulation: buffers into internal RX buffer (loopback).
        """
        iq_arr = np.asarray(iq, dtype=np.complex64).flatten()
        if len(iq_arr) == 0:
            return

        if self._is_simulation or self._sdr is None:
            self._sim_transmit(iq_arr)
            return

        try:
            self._sdr.tx(iq_arr)
            self._tx_sample_count += len(iq_arr)
        except Exception as e:
            self._last_error = f"TX error: {e}"

    def health(self) -> DeviceHealth:
        return DeviceHealth(
            connected=not self._is_simulation and self._sdr is not None,
            uri=self._uri,
            temperature_c=0.0,
            last_sample_time_s=time.perf_counter(),
            dropped_samples=self._dropped_samples,
            buffer_depth=len(self._sim_rx_buffer) if self._is_simulation else 0,
            errors=([self._last_error] if self._last_error else []),
        )

    def set_frequency(self, freq_hz: float):
        """Change RX/TX LO frequency at runtime (for frequency hopping)."""
        if self._is_simulation or self._sdr is None:
            return
        try:
            if self._rx_config:
                self._sdr.rx_lo = int(freq_hz)
            if self._tx_config:
                self._sdr.tx_lo = int(freq_hz)
        except Exception:
            pass

    def set_gain(self, gain_db: float):
        """Change RX gain at runtime (for TDD protection)."""
        if self._is_simulation or self._sdr is None:
            return
        try:
            self._sdr.gain_control_mode_chan0 = "manual"
            self._sdr.rx_hardwaregain_chan0 = gain_db
        except Exception:
            pass

    def measure_rx_power_db(self, num_samples: int = 4096) -> float:
        """Quick RX power measurement for CCA (dB full-scale)."""
        samples = self.receive(num_samples)
        if len(samples) == 0:
            return -100.0
        power_linear = np.mean(np.abs(samples) ** 2)
        if power_linear < 1e-20:
            return -100.0
        return float(10.0 * math.log10(power_linear))

    def enable_rx(self, enable: bool):
        """Enable or disable RX chain (TDD protection)."""
        if self._is_simulation or self._sdr is None:
            return
        if not enable:
            self.set_gain(-20.0)
        elif self._rx_config:
            self.set_gain(self._rx_config.gain_db)

    @property
    def is_simulation(self) -> bool:
        return self._is_simulation

    @property
    def uri(self) -> str:
        return self._uri

    @property
    def sample_rate_hz(self) -> float:
        return self._sample_rate_hz

    def _sim_receive(self, num_samples: int) -> np.ndarray:
        if len(self._sim_rx_buffer) == 0:
            self._dropped_samples += num_samples
            return np.zeros(num_samples, dtype=np.complex64)

        n = min(num_samples, len(self._sim_rx_buffer))
        result = self._sim_rx_buffer[:n].copy()
        self._sim_rx_buffer = self._sim_rx_buffer[n:]
        return result

    def _sim_transmit(self, iq: np.ndarray):
        self._sim_rx_buffer = np.concatenate([
            self._sim_rx_buffer, iq.astype(np.complex64)
        ])

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        """Release SDR resources."""
        if self._sdr is not None:
            try:
                del self._sdr
            except Exception:
                pass
            self._sdr = None
        self._initialized = False


class PlutoSDRFactory:
    """Factory for creating PlutoSDR device pairs for competition.

    Creates TX and RX devices with appropriate configurations
    for the single-filter competition setup.
    """

    @staticmethod
    def create_pair(
        tx_uri: str = "ip:192.168.2.1",
        rx_uri: str = "ip:192.168.2.1",
        center_freq_hz: float = 2.45e9,
        sample_rate_hz: float = 2.0e6,
        tx_gain_db: float = -10.0,
        rx_gain_db: float = 40.0,
    ) -> tuple[PlutoSDRDevice, PlutoSDRDevice]:
        """Create TX and RX device pair.

        TX device: includes 2.4GHz BPF in external RF path
        RX device: bare (no external filter, TDD-protected)

        Returns:
            (tx_device, rx_device) tuple.
        """
        tx = PlutoSDRDevice(uri=tx_uri, sample_rate_hz=sample_rate_hz)
        rx = PlutoSDRDevice(uri=rx_uri, sample_rate_hz=sample_rate_hz)

        tx.configure_tx(TxHardwareConfig(
            uri=tx_uri,
            center_frequency_hz=center_freq_hz,
            sample_rate_hz=sample_rate_hz,
            rf_bandwidth_hz=sample_rate_hz,
            attenuation_db=-tx_gain_db,
            buffer_size_samples=32768,
        ))

        rx.configure_rx(RxHardwareConfig(
            uri=rx_uri,
            center_frequency_hz=center_freq_hz,
            sample_rate_hz=sample_rate_hz,
            rf_bandwidth_hz=sample_rate_hz,
            gain_mode="manual",
            gain_db=rx_gain_db,
            buffer_size_samples=32768,
        ))

        return tx, rx


def is_pluto_available() -> bool:
    """Check if PlutoSDR hardware can be accessed."""
    return _adi_available
