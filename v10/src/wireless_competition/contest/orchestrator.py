"""Competition orchestrator.

Integrates all subsystems for the contest scenario:
- Fountain codes (no-ACK file transfer)
- TDD MAC (timing + CCA + frequency hopping)
- DSSS with Gold codes (CDMA + anti-jamming)
- PlutoSDR (real or simulated hardware)

Two operation modes:
1. Transmitter: reads file → fountain encode → DSSS spread → TX SDR
2. Receiver: RX SDR → DSSS despread → fountain decode → write file

Both sides run independently. The receiver collects enough fountain
packets to decode the file without any acknowledgements.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

import numpy as np

from ..common.buffer import HealthMonitor, RingBuffer
from ..common.seeds import create_rng
from ..common.types import DeviceHealth, RxHardwareConfig, TxHardwareConfig
from ..fountain.raptorq import (
    FountainDecoder,
    FountainEncoder,
    FountainPacket,
    fountain_encode_file,
)
from ..mac.tdd import (
    CCAReport,
    FrequencyHopper,
    SlotType,
    TDDConfig,
    TDDController,
    create_competition_tdd_config,
)
from ..sdr.base import SDRDevice, SimulatedSDRDevice
from ..sdr.pluto import PlutoSDRDevice, PlutoSDRFactory

from .dsss_pipeline import (
    ContestDSSSDecoder,
    ContestDSSSEncoder,
    DSSSConfig,
    create_contest_dsss,
)


class OrchestratorState(Enum):
    IDLE = "idle"
    SCANNING = "scanning"
    TRANSMITTING = "transmitting"
    RECEIVING = "receiving"
    DECODING = "decoding"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class ContestConfig:
    """Complete competition configuration."""
    team_id: int = 0
    file_id: int = 0

    tx_uri: str = "ip:192.168.2.1"
    rx_uri: str = "ip:192.168.2.1"

    center_frequency_hz: float = 2.45e9
    sample_rate_hz: float = 2.0e6
    rf_bandwidth_hz: float = 2.0e6

    tx_gain_db: float = -10.0
    rx_gain_db: float = 40.0

    block_size: int = 256
    spreading_factor: int = 128

    tdd: TDDConfig = field(default_factory=create_competition_tdd_config)
    dsss: DSSSConfig = field(default_factory=DSSSConfig)

    rx_buffer_size: int = 65536
    max_packet_size_bytes: int = 1024

    output_dir: str = "contest_output"
    log_interval_s: float = 1.0

    sim_mode: bool = False

    def __post_init__(self):
        self.dsss.team_id = self.team_id
        self.dsss.spreading_factor = self.spreading_factor

    def validate(self) -> list[str]:
        issues = []
        tdd_issues = self.tdd.validate()
        issues.extend(tdd_issues)
        if self.spreading_factor < 16:
            issues.append(f"Spreading factor too low: {self.spreading_factor}")
        if self.spreading_factor > 2048:
            issues.append(f"Spreading factor too high: {self.spreading_factor}")
        if self.sample_rate_hz < 100e3:
            issues.append(f"Sample rate too low: {self.sample_rate_hz} Hz")
        if self.sample_rate_hz > 61.44e6:
            issues.append(f"Sample rate too high: {self.sample_rate_hz} Hz")
        return issues

    def to_dict(self) -> dict:
        return {
            "team_id": self.team_id,
            "file_id": self.file_id,
            "tx_uri": self.tx_uri,
            "rx_uri": self.rx_uri,
            "center_frequency_hz": self.center_frequency_hz,
            "sample_rate_hz": self.sample_rate_hz,
            "rf_bandwidth_hz": self.rf_bandwidth_hz,
            "spreading_factor": self.spreading_factor,
            "block_size": self.block_size,
            "sim_mode": self.sim_mode,
        }


@dataclass
class ContestStatus:
    """Runtime status of the contest orchestrator."""
    state: OrchestratorState = OrchestratorState.IDLE
    team_id: int = 0

    packets_sent: int = 0
    packets_received: int = 0
    packets_unique: int = 0
    blocks_decoded: int = 0
    total_blocks: int = 0

    current_frequency_hz: float = 0.0
    current_slot: str = "idle"
    cca_result: Optional[CCAReport] = None

    file_complete: bool = False
    bytes_recovered: int = 0
    bytes_total: int = 0
    goodput_bps: float = 0.0

    elapsed_time_s: float = 0.0
    last_error: str = ""

    tx_health: DeviceHealth = field(default_factory=DeviceHealth)
    rx_health: DeviceHealth = field(default_factory=DeviceHealth)

    def summary(self) -> str:
        lines = [
            f"Team {self.team_id} | State: {self.state.value}",
            f"Frequency: {self.current_frequency_hz / 1e6:.3f} MHz | Slot: {self.current_slot}",
            f"Packets: sent={self.packets_sent} rx={self.packets_received} unique={self.packets_unique}",
            f"Blocks: {self.blocks_decoded}/{self.total_blocks} decoded",
            f"File: {self.bytes_recovered}/{self.bytes_total} bytes "
            f"({'COMPLETE' if self.file_complete else 'incomplete'})",
            f"Goodput: {self.goodput_bps:.0f} bps | Time: {self.elapsed_time_s:.1f}s",
        ]
        if self.last_error:
            lines.append(f"Last error: {self.last_error}")
        return "\n".join(lines)


class ContestOrchestrator:
    """Main competition orchestrator.

    Coordinates TX and RX SDR devices, TDD MAC timing, fountain coding,
    and DSSS spread spectrum to reliably transfer files in contested spectrum.

    Usage:
        config = ContestConfig(team_id=0)

        # Transmitter mode
        tx = ContestOrchestrator(config)
        tx.transmit_file("input.bin")

        # Receiver mode (separate process/SDR pair)
        rx = ContestOrchestrator(config)
        rx.receive_file("output.bin")
    """

    def __init__(self, config: ContestConfig):
        self.config = config
        self._status = ContestStatus(
            team_id=config.team_id,
            state=OrchestratorState.IDLE,
        )

        self._tdd = TDDController(config.tdd)
        self._rng = create_rng(config.team_id)

        if config.sim_mode:
            self._tx_sdr: SDRDevice = SimulatedSDRDevice(config.sample_rate_hz)
            self._rx_sdr: SDRDevice = SimulatedSDRDevice(config.sample_rate_hz)
        else:
            self._tx_sdr = PlutoSDRDevice(
                uri=config.tx_uri,
                sample_rate_hz=config.sample_rate_hz,
            )
            self._rx_sdr = PlutoSDRDevice(
                uri=config.rx_uri,
                sample_rate_hz=config.sample_rate_hz,
            )

        tx_hw = TxHardwareConfig(
            uri=config.tx_uri,
            center_frequency_hz=config.center_frequency_hz,
            sample_rate_hz=config.sample_rate_hz,
            rf_bandwidth_hz=config.rf_bandwidth_hz,
            attenuation_db=-config.tx_gain_db,
            buffer_size_samples=config.rx_buffer_size // 2,
        )
        rx_hw = RxHardwareConfig(
            uri=config.rx_uri,
            center_frequency_hz=config.center_frequency_hz,
            sample_rate_hz=config.sample_rate_hz,
            rf_bandwidth_hz=config.rf_bandwidth_hz,
            gain_mode="manual",
            gain_db=config.rx_gain_db,
            buffer_size_samples=config.rx_buffer_size // 2,
        )

        self._tx_sdr.configure_tx(tx_hw)
        self._rx_sdr.configure_rx(rx_hw)

        self._dsss_encoder, self._dsss_decoder = create_contest_dsss(
            config.team_id, config.spreading_factor,
        )

        self._fountain_decoder = FountainDecoder()
        self._fountain_encoder: Optional[FountainEncoder] = None

        self._rx_buffer = RingBuffer(
            capacity=config.rx_buffer_size * 4, dtype=np.complex64,
        )
        self._health_monitor = HealthMonitor()

        self._running = False
        self._start_time = 0.0
        self._log_interval = config.log_interval_s
        self._last_log_time = 0.0

        self._output_file: str = ""
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, sig, frame):
        self._running = False
        print("\nShutting down...")

    @property
    def status(self) -> ContestStatus:
        return self._status

    def transmit_file(self, file_path: str) -> ContestStatus:
        """Transmit a file using fountain codes + DSSS over the air.

        Runs until the file has been fully transmitted (all systematic
        packets sent + repair packets for a configurable overhead).
        """
        if not os.path.exists(file_path):
            self._status.state = OrchestratorState.ERROR
            self._status.last_error = f"File not found: {file_path}"
            return self._status

        self._start_time = time.monotonic()
        self._running = True
        self._status.state = OrchestratorState.TRANSMITTING

        self._fountain_encoder = fountain_encode_file(
            file_path,
            block_size=self.config.block_size,
            file_id=self.config.file_id,
        )

        total_blocks = self._fountain_encoder.source_blocks
        total_size = self._fountain_encoder.total_size
        self._status.total_blocks = total_blocks
        self._status.bytes_total = total_size

        print(f"TX: {total_blocks} blocks, {total_size} bytes, "
              f"SF={self.config.spreading_factor} "
              f"({self.config.dsss.processing_gain_db:.1f} dB PG)")

        self._tdd.start_superframe()

        # Send systematic packets first, then repair
        packet_iter = iter(self._fountain_encoder.encode_systematic_stream())
        max_packets = total_blocks + 500

        try:
            while self._running and self._status.packets_sent < max_packets:
                if self._tdd.current_slot in (SlotType.GUARD, SlotType.CCA):
                    if self._tdd.current_slot == SlotType.CCA:
                        power = self._rx_sdr.measure_rx_power_db(2048)
                        cca = self._tdd.perform_cca(power)
                        self._status.cca_result = cca
                        if cca.channel_free:
                            self._tdd.advance_slot()
                        else:
                            self._tdd.backoff()
                            self._tdd.advance_slot()
                    else:
                        self._tdd.advance_slot()
                    self._update_slot_status()
                    continue

                elif self._tdd.current_slot == SlotType.TX:
                    self._tx_slot(packet_iter)
                    self._tdd.advance_slot()

                elif self._tdd.current_slot == SlotType.RX:
                    self._tdd.advance_slot()

                self._update_slot_status()

                if self._status.packets_sent >= total_blocks + 50:
                    if self._status.packets_sent % 100 == 0:
                        self._log_status()

        except Exception as e:
            self._status.state = OrchestratorState.ERROR
            self._status.last_error = str(e)
        finally:
            self._running = False

        self._status.elapsed_time_s = time.monotonic() - self._start_time
        self._status.state = OrchestratorState.COMPLETE
        self._log_status()
        return self._status

    def _tx_slot(self, packet_iter):
        """Transmit during a TX slot."""
        try:
            pkt = next(packet_iter)
        except StopIteration:
            return

        iq = self._dsss_encoder.encode_packet(pkt)

        if isinstance(self._tx_sdr, PlutoSDRDevice) and not self._tx_sdr.is_simulation:
            freq = self._tdd.current_frequency
            self._tx_sdr.set_frequency(freq)

        self._tx_sdr.transmit(iq)
        self._status.packets_sent += 1
        self._status.current_frequency_hz = self._tdd.current_frequency

    def receive_file(self, output_path: str = "") -> ContestStatus:
        """Receive and decode a file transmitted via fountain codes + DSSS.

        Continuously listens on the RX SDR, despreads incoming DSSS
        signals, extracts fountain packets, and attempts to decode
        the file once enough packets are collected.
        """
        self._output_file = output_path or os.path.join(
            self.config.output_dir,
            f"recovered_team{self.config.team_id}_{int(time.time())}.bin",
        )

        os.makedirs(os.path.dirname(self._output_file) or ".", exist_ok=True)

        self._start_time = time.monotonic()
        self._running = True
        self._status.state = OrchestratorState.RECEIVING

        print(f"RX: listening on {self.config.center_frequency_hz / 1e6:.1f} MHz...")

        self._tdd.start_superframe()

        try:
            while self._running:
                if self._tdd.current_slot in (SlotType.GUARD, SlotType.CCA):
                    if self._tdd.current_slot == SlotType.CCA:
                        power = self._rx_sdr.measure_rx_power_db(2048)
                        self._tdd.perform_cca(power)
                    self._tdd.advance_slot()
                    self._update_slot_status()
                    continue

                elif self._tdd.current_slot == SlotType.TX:
                    self._tdd.advance_slot()
                    continue

                elif self._tdd.current_slot == SlotType.RX:
                    self._rx_slot()
                    self._tdd.advance_slot()

                self._update_slot_status()

                if self._fountain_decoder.is_k_known:
                    if self._fountain_decoder.can_decode():
                        data = self._fountain_decoder.decode()
                        if data is not None:
                            self._on_decode_complete(data)

                self._periodic_log()

        except Exception as e:
            self._status.state = OrchestratorState.ERROR
            self._status.last_error = str(e)
        finally:
            self._running = False

        self._status.elapsed_time_s = time.monotonic() - self._start_time
        return self._status

    def _rx_slot(self):
        """Receive and process IQ samples during an RX slot."""
        buf_size = self.config.rx_buffer_size // 2

        raw_iq = self._rx_sdr.receive(buf_size)
        if len(raw_iq) == 0:
            return

        packets = self._dsss_decoder.process_stream(raw_iq)
        for pkt in packets:
            self._fountain_decoder.add_packet(pkt)
            self._status.packets_received += 1
            self._status.packets_unique = self._fountain_decoder.num_collected

        if self._fountain_decoder.is_k_known:
            self._status.total_blocks = self._fountain_decoder.k
            self._status.blocks_decoded = self._fountain_decoder.num_decoded

    def _on_decode_complete(self, data: bytes):
        """Called when fountain decoding succeeds."""
        self._status.bytes_recovered = len(data)
        self._status.file_complete = True

        try:
            with open(self._output_file, "wb") as f:
                f.write(data)
            file_hash = hashlib.sha256(data).hexdigest()[:16]
            self._status.state = OrchestratorState.COMPLETE
            actual_size = os.path.getsize(self._output_file)
            self._log_status()
            print(f"\nFile recovered: {self._output_file}")
            print(f"  Size: {actual_size} bytes")
            print(f"  SHA256: {file_hash}")
            print(f"  Time: {self._status.elapsed_time_s:.2f}s")
            print(f"  Goodput: {self._status.goodput_bps:.0f} bps")
            self._running = False
        except Exception as e:
            self._status.last_error = f"File write error: {e}"

    def _update_slot_status(self):
        self._status.current_slot = self._tdd.current_slot.value
        self._status.current_frequency_hz = self._tdd.current_frequency
        self._status.tx_health = self._tx_sdr.health()
        self._status.rx_health = self._rx_sdr.health()
        elapsed = time.monotonic() - self._start_time
        self._status.elapsed_time_s = elapsed
        if elapsed > 0 and self._status.bytes_recovered > 0:
            self._status.goodput_bps = (self._status.bytes_recovered * 8) / elapsed

    def _periodic_log(self):
        now = time.monotonic()
        if now - self._last_log_time >= self._log_interval:
            self._log_status()
            self._last_log_time = now

    def _log_status(self):
        elapsed = self._status.elapsed_time_s
        print(
            f"\r[{elapsed:6.1f}s] "
            f"Pkts: s={self._status.packets_sent} "
            f"r={self._status.packets_received} "
            f"u={self._status.packets_unique} "
            f"| Blks: {self._status.blocks_decoded}/{self._status.total_blocks}"
            f" | {self._status.current_frequency_hz / 1e6:.3f} MHz"
            f" | {self._status.current_slot}",
            end="",
            flush=True,
        )

    def stop(self):
        """Gracefully stop the orchestrator."""
        self._running = False

    def close(self):
        """Release all resources."""
        self.stop()
        if hasattr(self._tx_sdr, 'close'):
            self._tx_sdr.close()
        if hasattr(self._rx_sdr, 'close'):
            self._rx_sdr.close()

    def run_simulation_e2e(
        self,
        file_path: str,
        output_path: str = "",
        snr_db: float = 20.0,
    ) -> ContestStatus:
        """Run end-to-end simulation (TX → Channel → RX in-memory).

        Uses SimulatedSDRDevice for TX/RX, adds AWGN channel between them.
        Useful for testing the complete pipeline without hardware.
        """
        from ..channel.pipeline import ChannelPipeline
        from ..common.types import ChannelConfig, InterferenceFamily

        self._start_time = time.monotonic()
        self._running = True

        self._fountain_encoder = fountain_encode_file(
            file_path, block_size=self.config.block_size, file_id=self.config.file_id,
        )
        total_blocks = self._fountain_encoder.source_blocks
        total_size = self._fountain_encoder.total_size
        self._status.total_blocks = total_blocks
        self._status.bytes_total = total_size

        channel = ChannelPipeline(ChannelConfig(
            snr_db=snr_db,
            enable_awgn=True,
            enable_interference=True,
            interference_type=InterferenceFamily.TONE,
            inr_db=-10.0,
        ))

        max_packets = total_blocks + 200

        packet_iter = iter(self._fountain_encoder.encode_systematic_stream())

        try:
            while self._running and self._status.packets_sent < max_packets:
                try:
                    pkt = next(packet_iter)
                except StopIteration:
                    break

                tx_iq = self._dsss_encoder.encode_packet(pkt)
                self._tx_sdr.transmit(tx_iq)
                self._status.packets_sent += 1

                ch_out = channel.apply(tx_iq, sample_rate_hz=self.config.sample_rate_hz, rng=self._rng)
                rx_data = self._rx_sdr.receive(len(ch_out.iq))
                if len(rx_data) > 0:
                    pass

                self._sim_receive_buffer = np.concatenate([
                    getattr(self, '_sim_receive_buffer', np.array([], dtype=np.complex64)),
                    ch_out.iq,
                ])

                if len(self._sim_receive_buffer) > self.config.rx_buffer_size:
                    to_process = self._sim_receive_buffer[:self.config.rx_buffer_size]
                    self._sim_receive_buffer = self._sim_receive_buffer[self.config.rx_buffer_size // 2:]

                    packets = self._dsss_decoder.process_stream(to_process)
                    for fp in packets:
                        self._fountain_decoder.add_packet(fp)
                        self._status.packets_received += 1
                        self._status.packets_unique = self._fountain_decoder.num_collected
                        self._status.total_blocks = self._fountain_decoder.k or 0
                        self._status.blocks_decoded = self._fountain_decoder.num_decoded

                    if self._fountain_decoder.can_decode():
                        data = self._fountain_decoder.decode()
                        if data is not None:
                            self._status.bytes_recovered = len(data)
                            self._status.file_complete = True
                            self._status.state = OrchestratorState.COMPLETE

                            if output_path:
                                os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
                                with open(output_path, "wb") as f:
                                    f.write(data)

                            self._status.elapsed_time_s = time.monotonic() - self._start_time
                            self._running = False
                            return self._status

        except Exception as e:
            self._status.state = OrchestratorState.ERROR
            self._status.last_error = str(e)
        finally:
            self._running = False
            self._status.elapsed_time_s = time.monotonic() - self._start_time

        return self._status


def create_team_orchestrator(
    team_id: int,
    file_id: int = 0,
    sim_mode: bool = False,
    tx_uri: str = "ip:192.168.2.1",
    rx_uri: str = "ip:192.168.2.1",
) -> ContestOrchestrator:
    """Factory: create a complete orchestrator for a competition team.

    Args:
        team_id: Unique team identifier (determines Gold code shift).
        file_id: File identifier.
        sim_mode: Use simulation instead of real hardware.
        tx_uri: PlutoSDR TX device URI.
        rx_uri: PlutoSDR RX device URI.

    Returns:
        Configured ContestOrchestrator ready for transmit_file() or receive_file().
    """
    config = ContestConfig(
        team_id=team_id,
        file_id=file_id,
        tx_uri=tx_uri,
        rx_uri=rx_uri,
        sim_mode=sim_mode,
        tdd=create_competition_tdd_config(team_id),
    )
    return ContestOrchestrator(config)
