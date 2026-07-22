#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: SDR Contest Complete File Link
# Author: Competition Team
# Copyright: 2026
# Description: CRC/FEC 文件分帧 -> BPSK/QPSK + RRC -> 可复现信道/干扰 -> 同步解调/CRC/去重重组；含 IQ 记录与受控 pyadi-iio 硬件接口。
# GNU Radio version: 3.10.12.0

from gnuradio import blocks
from gnuradio import channels
from gnuradio.filter import firdes
from gnuradio import gr
from gnuradio.fft import window
import sys
import signal
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation
import sdr_contest_complete_contest_pluto_tx_sink as contest_pluto_tx_sink  # embedded python block
import sdr_contest_complete_contest_rx_sink as contest_rx_sink  # embedded python block
import sdr_contest_complete_contest_rx_source as contest_rx_source  # embedded python block
import sdr_contest_complete_contest_tx_source as contest_tx_source  # embedded python block
import sdr_contest_complete_interference_impairments as interference_impairments  # embedded python block
import threading




class sdr_contest_complete(gr.top_block):

    def __init__(self):
        gr.top_block.__init__(self, "SDR Contest Complete File Link", catch_exceptions=True)
        self.flowgraph_started = threading.Event()

        ##################################################
        # Variables
        ##################################################
        self.tx_scale = tx_scale = 0.5
        self.snr_db = snr_db = 30.0
        self.role = role = 'sim'
        self.tx_manifest_path = tx_manifest_path = 'tx_manifest.json'
        self.tx_attenuation_db = tx_attenuation_db = -89.75
        self.tone_offset_hz = tone_offset_hz = 100000.0
        self.tone_inr_db = tone_inr_db = -120.0
        self.sro_ppm = sro_ppm = 0.0
        self.seed = seed = 42
        self.samples_per_symbol = samples_per_symbol = 8
        self.samp_rate = samp_rate = 2000000
        self.rx_gain_mode = rx_gain_mode = 'manual'
        self.rx_gain_db = rx_gain_db = 30.0
        self.rules_path = rules_path = 'contest_rules.yaml'
        self.rules_confirmed = rules_confirmed = False
        self.rrc_span = rrc_span = 6
        self.rrc_rolloff = rrc_rolloff = 0.35
        self.role_index = role_index = 0 if role == 'sim' else 1
        self.rf_enable = rf_enable = False
        self.rf_duration_s = rf_duration_s = 5.0
        self.rf_buffer_samples = rf_buffer_samples = 32768
        self.rf_bandwidth_hz = rf_bandwidth_hz = 1000000
        self.replay_path = replay_path = 'rx_capture.c64'
        self.preamble_symbols = preamble_symbols = 64
        self.physical_path_confirmed = physical_path_confirmed = False
        self.output_path = output_path = 'decoded_payload.bin'
        self.noise_voltage = noise_voltage = tx_scale * 10**(-snr_db/20.0)
        self.modulation = modulation = 'bpsk'
        self.metrics_path = metrics_path = 'run_metrics.json'
        self.max_capture_samples = max_capture_samples = 10000000
        self.iq_capture_path = iq_capture_path = 'rx_capture.c64'
        self.input_path = input_path = 'input_payload.bin'
        self.guard_symbols = guard_symbols = 16
        self.fec_mode = fec_mode = 'convolutional'
        self.device_uri = device_uri = 'ip:192.168.2.1'
        self.clipping_threshold = clipping_threshold = 0.95
        self.channel_taps = channel_taps = [1.0+0.0j]
        self.cfo_hz = cfo_hz = 0.0
        self.center_frequency_hz = center_frequency_hz = 0
        self.burst_probability = burst_probability = 0.0
        self.burst_inr_db = burst_inr_db = 10.0
        self.block_size = block_size = 256

        ##################################################
        # Blocks
        ##################################################

        self.tx_throttle = blocks.throttle(gr.sizeof_gr_complex*1, samp_rate,False)
        self.rx_selector = blocks.selector(gr.sizeof_gr_complex*1,role_index,0)
        self.rx_selector.set_enabled(True)
        self.rx_iq_capture = blocks.file_sink(gr.sizeof_gr_complex*1, iq_capture_path, False)
        self.rx_iq_capture.set_unbuffered(False)
        self.interference_impairments = interference_impairments.blk(role=role, samp_rate=samp_rate, reference_amplitude=tx_scale, tone_inr_db=tone_inr_db, tone_offset_hz=tone_offset_hz, burst_probability=burst_probability, burst_inr_db=burst_inr_db, clipping_threshold=clipping_threshold, iq_gain_db=0.0, iq_phase_deg=0.0, dc_real=0.0, dc_imag=0.0, seed=seed)
        self.contest_tx_source = contest_tx_source.blk(role=role, input_path=input_path, manifest_path=tx_manifest_path, modulation=modulation, fec_mode=fec_mode, samp_rate=samp_rate, samples_per_symbol=samples_per_symbol, rolloff=rrc_rolloff, span=rrc_span, block_size=block_size, preamble_symbols=preamble_symbols, guard_symbols=guard_symbols, seed=seed, tx_scale=tx_scale)
        self.contest_rx_source = contest_rx_source.blk(role=role, replay_path=replay_path, device_uri=device_uri, samp_rate=samp_rate, center_frequency_hz=center_frequency_hz, rf_bandwidth_hz=rf_bandwidth_hz, rx_gain_mode=rx_gain_mode, rx_gain_db=rx_gain_db, rx_buffer_samples=rf_buffer_samples, rf_duration_s=rf_duration_s, max_capture_samples=max_capture_samples, device_manifest_path='rx_device_manifest.json')
        self.contest_rx_sink = contest_rx_sink.blk(role=role, output_path=output_path, metrics_path=metrics_path, input_path=input_path, modulation=modulation, fec_mode=fec_mode, samp_rate=samp_rate, samples_per_symbol=samples_per_symbol, rolloff=rrc_rolloff, span=rrc_span, preamble_symbols=preamble_symbols, guard_symbols=guard_symbols, detection_threshold=0.45, max_capture_samples=max_capture_samples, use_frame_tags=abs(sro_ppm) < 1e-12, seed=seed)
        self.contest_pluto_tx_sink = contest_pluto_tx_sink.blk(role=role, rf_enable=rf_enable, rules_confirmed=rules_confirmed, physical_path_confirmed=physical_path_confirmed, rules_path=rules_path, device_uri=device_uri, samp_rate=samp_rate, center_frequency_hz=center_frequency_hz, rf_bandwidth_hz=rf_bandwidth_hz, tx_attenuation_db=tx_attenuation_db, rf_duration_s=rf_duration_s, tx_buffer_samples=rf_buffer_samples)
        self.channel_model = channels.channel_model(
            noise_voltage=noise_voltage,
            frequency_offset=(cfo_hz / samp_rate),
            epsilon=(1.0 + sro_ppm * 1e-6),
            taps=channel_taps,
            noise_seed=seed,
            block_tags=False)


        ##################################################
        # Connections
        ##################################################
        self.connect((self.channel_model, 0), (self.interference_impairments, 0))
        self.connect((self.contest_rx_source, 0), (self.rx_selector, 1))
        self.connect((self.contest_tx_source, 0), (self.tx_throttle, 0))
        self.connect((self.interference_impairments, 0), (self.rx_selector, 0))
        self.connect((self.rx_selector, 0), (self.contest_rx_sink, 0))
        self.connect((self.rx_selector, 0), (self.rx_iq_capture, 0))
        self.connect((self.tx_throttle, 0), (self.channel_model, 0))
        self.connect((self.tx_throttle, 0), (self.contest_pluto_tx_sink, 0))


    def get_tx_scale(self):
        return self.tx_scale

    def set_tx_scale(self, tx_scale):
        self.tx_scale = tx_scale
        self.set_noise_voltage(self.tx_scale * 10**(-self.snr_db/20.0))
        self.contest_tx_source.tx_scale = self.tx_scale
        self.interference_impairments.reference_amplitude = self.tx_scale

    def get_snr_db(self):
        return self.snr_db

    def set_snr_db(self, snr_db):
        self.snr_db = snr_db
        self.set_noise_voltage(self.tx_scale * 10**(-self.snr_db/20.0))

    def get_role(self):
        return self.role

    def set_role(self, role):
        self.role = role
        self.set_role_index(0 if self.role == 'sim' else 1)
        self.contest_pluto_tx_sink.role = self.role
        self.contest_rx_sink.role = self.role
        self.contest_rx_source.role = self.role
        self.contest_tx_source.role = self.role
        self.interference_impairments.role = self.role

    def get_tx_manifest_path(self):
        return self.tx_manifest_path

    def set_tx_manifest_path(self, tx_manifest_path):
        self.tx_manifest_path = tx_manifest_path
        self.contest_tx_source.manifest_path = self.tx_manifest_path

    def get_tx_attenuation_db(self):
        return self.tx_attenuation_db

    def set_tx_attenuation_db(self, tx_attenuation_db):
        self.tx_attenuation_db = tx_attenuation_db
        self.contest_pluto_tx_sink.tx_attenuation_db = self.tx_attenuation_db

    def get_tone_offset_hz(self):
        return self.tone_offset_hz

    def set_tone_offset_hz(self, tone_offset_hz):
        self.tone_offset_hz = tone_offset_hz
        self.interference_impairments.tone_offset_hz = self.tone_offset_hz

    def get_tone_inr_db(self):
        return self.tone_inr_db

    def set_tone_inr_db(self, tone_inr_db):
        self.tone_inr_db = tone_inr_db
        self.interference_impairments.tone_inr_db = self.tone_inr_db

    def get_sro_ppm(self):
        return self.sro_ppm

    def set_sro_ppm(self, sro_ppm):
        self.sro_ppm = sro_ppm
        self.channel_model.set_timing_offset((1.0 + self.sro_ppm * 1e-6))
        self.contest_rx_sink.use_frame_tags = abs(self.sro_ppm) < 1e-12

    def get_seed(self):
        return self.seed

    def set_seed(self, seed):
        self.seed = seed
        self.contest_rx_sink.seed = self.seed
        self.contest_tx_source.seed = self.seed
        self.interference_impairments.seed = self.seed

    def get_samples_per_symbol(self):
        return self.samples_per_symbol

    def set_samples_per_symbol(self, samples_per_symbol):
        self.samples_per_symbol = samples_per_symbol
        self.contest_rx_sink.samples_per_symbol = self.samples_per_symbol
        self.contest_tx_source.samples_per_symbol = self.samples_per_symbol

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.channel_model.set_frequency_offset((self.cfo_hz / self.samp_rate))
        self.contest_pluto_tx_sink.samp_rate = self.samp_rate
        self.contest_rx_sink.samp_rate = self.samp_rate
        self.contest_rx_source.samp_rate = self.samp_rate
        self.contest_tx_source.samp_rate = self.samp_rate
        self.interference_impairments.samp_rate = self.samp_rate
        self.tx_throttle.set_sample_rate(self.samp_rate)

    def get_rx_gain_mode(self):
        return self.rx_gain_mode

    def set_rx_gain_mode(self, rx_gain_mode):
        self.rx_gain_mode = rx_gain_mode
        self.contest_rx_source.rx_gain_mode = self.rx_gain_mode

    def get_rx_gain_db(self):
        return self.rx_gain_db

    def set_rx_gain_db(self, rx_gain_db):
        self.rx_gain_db = rx_gain_db
        self.contest_rx_source.rx_gain_db = self.rx_gain_db

    def get_rules_path(self):
        return self.rules_path

    def set_rules_path(self, rules_path):
        self.rules_path = rules_path
        self.contest_pluto_tx_sink.rules_path = self.rules_path

    def get_rules_confirmed(self):
        return self.rules_confirmed

    def set_rules_confirmed(self, rules_confirmed):
        self.rules_confirmed = rules_confirmed
        self.contest_pluto_tx_sink.rules_confirmed = self.rules_confirmed

    def get_rrc_span(self):
        return self.rrc_span

    def set_rrc_span(self, rrc_span):
        self.rrc_span = rrc_span
        self.contest_rx_sink.span = self.rrc_span
        self.contest_tx_source.span = self.rrc_span

    def get_rrc_rolloff(self):
        return self.rrc_rolloff

    def set_rrc_rolloff(self, rrc_rolloff):
        self.rrc_rolloff = rrc_rolloff
        self.contest_rx_sink.rolloff = self.rrc_rolloff
        self.contest_tx_source.rolloff = self.rrc_rolloff

    def get_role_index(self):
        return self.role_index

    def set_role_index(self, role_index):
        self.role_index = role_index
        self.rx_selector.set_input_index(self.role_index)

    def get_rf_enable(self):
        return self.rf_enable

    def set_rf_enable(self, rf_enable):
        self.rf_enable = rf_enable
        self.contest_pluto_tx_sink.rf_enable = self.rf_enable

    def get_rf_duration_s(self):
        return self.rf_duration_s

    def set_rf_duration_s(self, rf_duration_s):
        self.rf_duration_s = rf_duration_s
        self.contest_pluto_tx_sink.rf_duration_s = self.rf_duration_s
        self.contest_rx_source.rf_duration_s = self.rf_duration_s

    def get_rf_buffer_samples(self):
        return self.rf_buffer_samples

    def set_rf_buffer_samples(self, rf_buffer_samples):
        self.rf_buffer_samples = rf_buffer_samples
        self.contest_pluto_tx_sink.tx_buffer_samples = self.rf_buffer_samples
        self.contest_rx_source.rx_buffer_samples = self.rf_buffer_samples

    def get_rf_bandwidth_hz(self):
        return self.rf_bandwidth_hz

    def set_rf_bandwidth_hz(self, rf_bandwidth_hz):
        self.rf_bandwidth_hz = rf_bandwidth_hz
        self.contest_pluto_tx_sink.rf_bandwidth_hz = self.rf_bandwidth_hz
        self.contest_rx_source.rf_bandwidth_hz = self.rf_bandwidth_hz

    def get_replay_path(self):
        return self.replay_path

    def set_replay_path(self, replay_path):
        self.replay_path = replay_path
        self.contest_rx_source.replay_path = self.replay_path

    def get_preamble_symbols(self):
        return self.preamble_symbols

    def set_preamble_symbols(self, preamble_symbols):
        self.preamble_symbols = preamble_symbols
        self.contest_rx_sink.preamble_symbols = self.preamble_symbols
        self.contest_tx_source.preamble_symbols = self.preamble_symbols

    def get_physical_path_confirmed(self):
        return self.physical_path_confirmed

    def set_physical_path_confirmed(self, physical_path_confirmed):
        self.physical_path_confirmed = physical_path_confirmed
        self.contest_pluto_tx_sink.physical_path_confirmed = self.physical_path_confirmed

    def get_output_path(self):
        return self.output_path

    def set_output_path(self, output_path):
        self.output_path = output_path
        self.contest_rx_sink.output_path = self.output_path

    def get_noise_voltage(self):
        return self.noise_voltage

    def set_noise_voltage(self, noise_voltage):
        self.noise_voltage = noise_voltage
        self.channel_model.set_noise_voltage(self.noise_voltage)

    def get_modulation(self):
        return self.modulation

    def set_modulation(self, modulation):
        self.modulation = modulation
        self.contest_rx_sink.modulation = self.modulation
        self.contest_tx_source.modulation = self.modulation

    def get_metrics_path(self):
        return self.metrics_path

    def set_metrics_path(self, metrics_path):
        self.metrics_path = metrics_path
        self.contest_rx_sink.metrics_path = self.metrics_path

    def get_max_capture_samples(self):
        return self.max_capture_samples

    def set_max_capture_samples(self, max_capture_samples):
        self.max_capture_samples = max_capture_samples
        self.contest_rx_sink.max_capture_samples = self.max_capture_samples
        self.contest_rx_source.max_capture_samples = self.max_capture_samples

    def get_iq_capture_path(self):
        return self.iq_capture_path

    def set_iq_capture_path(self, iq_capture_path):
        self.iq_capture_path = iq_capture_path
        self.rx_iq_capture.open(self.iq_capture_path)

    def get_input_path(self):
        return self.input_path

    def set_input_path(self, input_path):
        self.input_path = input_path
        self.contest_rx_sink.input_path = self.input_path
        self.contest_tx_source.input_path = self.input_path

    def get_guard_symbols(self):
        return self.guard_symbols

    def set_guard_symbols(self, guard_symbols):
        self.guard_symbols = guard_symbols
        self.contest_rx_sink.guard_symbols = self.guard_symbols
        self.contest_tx_source.guard_symbols = self.guard_symbols

    def get_fec_mode(self):
        return self.fec_mode

    def set_fec_mode(self, fec_mode):
        self.fec_mode = fec_mode
        self.contest_rx_sink.fec_mode = self.fec_mode
        self.contest_tx_source.fec_mode = self.fec_mode

    def get_device_uri(self):
        return self.device_uri

    def set_device_uri(self, device_uri):
        self.device_uri = device_uri
        self.contest_pluto_tx_sink.device_uri = self.device_uri
        self.contest_rx_source.device_uri = self.device_uri

    def get_clipping_threshold(self):
        return self.clipping_threshold

    def set_clipping_threshold(self, clipping_threshold):
        self.clipping_threshold = clipping_threshold
        self.interference_impairments.clipping_threshold = self.clipping_threshold

    def get_channel_taps(self):
        return self.channel_taps

    def set_channel_taps(self, channel_taps):
        self.channel_taps = channel_taps
        self.channel_model.set_taps(self.channel_taps)

    def get_cfo_hz(self):
        return self.cfo_hz

    def set_cfo_hz(self, cfo_hz):
        self.cfo_hz = cfo_hz
        self.channel_model.set_frequency_offset((self.cfo_hz / self.samp_rate))

    def get_center_frequency_hz(self):
        return self.center_frequency_hz

    def set_center_frequency_hz(self, center_frequency_hz):
        self.center_frequency_hz = center_frequency_hz
        self.contest_pluto_tx_sink.center_frequency_hz = self.center_frequency_hz
        self.contest_rx_source.center_frequency_hz = self.center_frequency_hz

    def get_burst_probability(self):
        return self.burst_probability

    def set_burst_probability(self, burst_probability):
        self.burst_probability = burst_probability
        self.interference_impairments.burst_probability = self.burst_probability

    def get_burst_inr_db(self):
        return self.burst_inr_db

    def set_burst_inr_db(self, burst_inr_db):
        self.burst_inr_db = burst_inr_db
        self.interference_impairments.burst_inr_db = self.burst_inr_db

    def get_block_size(self):
        return self.block_size

    def set_block_size(self, block_size):
        self.block_size = block_size
        self.contest_tx_source.block_size = self.block_size




def main(top_block_cls=sdr_contest_complete, options=None):
    tb = top_block_cls()

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()

        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    tb.start()
    tb.flowgraph_started.set()

    try:
        input('Press Enter to quit: ')
    except EOFError:
        pass
    tb.stop()
    tb.wait()


if __name__ == '__main__':
    main()
