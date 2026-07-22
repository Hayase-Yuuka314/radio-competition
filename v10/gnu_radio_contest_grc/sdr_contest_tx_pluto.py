#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: SDR Contest PlutoSDR Transmitter
# Author: Competition Team
# Copyright: 2026
# Description: 占位信号/竞赛文件接口 -> 有限样本与授权门 -> 原生 PlutoSDR Sink
# GNU Radio version: 3.10.12.0

from gnuradio import analog
from gnuradio import blocks
from gnuradio import gr
from gnuradio.filter import firdes
from gnuradio.fft import window
import sys
import signal
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation
from gnuradio import iio
import sdr_contest_tx_pluto_contest_tx_source as contest_tx_source  # embedded python block
import sdr_contest_tx_pluto_tx_authorization_gate as tx_authorization_gate  # embedded python block
import threading


def snipfcn_tx_preflight(self):
    tx_authorization_gate.validate_tx_configuration(
        rf_enable=self.rf_enable,
        rules_confirmed=self.rules_confirmed,
        physical_path_confirmed=self.physical_path_confirmed,
        rules_path=self.rules_path,
        center_frequency_hz=self.center_frequency_hz,
        rf_bandwidth_hz=self.rf_bandwidth_hz,
        rf_duration_s=self.rf_duration_s,
        tx_attenuation_db=self.tx_attenuation_db,
    )


def snippets_init_before_blocks(tb):
    snipfcn_tx_preflight(tb)


class sdr_contest_tx_pluto(gr.top_block):

    def __init__(self):
        gr.top_block.__init__(self, "SDR Contest PlutoSDR Transmitter", catch_exceptions=True)
        self.flowgraph_started = threading.Event()

        ##################################################
        # Variables
        ##################################################
        self.samp_rate = samp_rate = 2000000
        self.rf_duration_s = rf_duration_s = 5.0
        self.input_mode = input_mode = 'placeholder'
        self.tx_scale = tx_scale = 0.5
        self.tx_manifest_path = tx_manifest_path = 'tx_manifest.json'
        self.tx_buffer_samples = tx_buffer_samples = 32768
        self.tx_attenuation_db = tx_attenuation_db = 89.75
        self.seed = seed = 42
        self.samples_per_symbol = samples_per_symbol = 8
        self.rules_path = rules_path = 'contest_rules.yaml'
        self.rules_confirmed = rules_confirmed = False
        self.rrc_span = rrc_span = 6
        self.rrc_rolloff = rrc_rolloff = 0.35
        self.rf_enable = rf_enable = False
        self.rf_bandwidth_hz = rf_bandwidth_hz = 1000000
        self.preamble_symbols = preamble_symbols = 64
        self.placeholder_frequency_hz = placeholder_frequency_hz = 100000.0
        self.placeholder_amplitude = placeholder_amplitude = 0.10
        self.physical_path_confirmed = physical_path_confirmed = False
        self.modulation = modulation = 'bpsk'
        self.max_tx_samples = max_tx_samples = min(int(rf_duration_s*samp_rate), 10000000)
        self.input_path = input_path = 'input_payload.bin'
        self.input_mode_index = input_mode_index = 0 if input_mode == 'placeholder' else 1
        self.guard_symbols = guard_symbols = 16
        self.fec_mode = fec_mode = 'convolutional'
        self.device_uri = device_uri = 'ip:192.168.2.1'
        self.center_frequency_hz = center_frequency_hz = 2400000000
        self.block_size = block_size = 256

        ##################################################
        # Blocks
        ##################################################
        snippets_init_before_blocks(self)
        self.tx_input_selector = blocks.selector(gr.sizeof_gr_complex*1,input_mode_index,0)
        self.tx_input_selector.set_enabled(True)
        self.tx_finite_head = blocks.head(gr.sizeof_gr_complex*1, max_tx_samples)
        self.tx_authorization_gate = tx_authorization_gate.blk(rf_enable=rf_enable, rules_confirmed=rules_confirmed, physical_path_confirmed=physical_path_confirmed, rules_path=rules_path, center_frequency_hz=center_frequency_hz, rf_bandwidth_hz=rf_bandwidth_hz, rf_duration_s=rf_duration_s, tx_attenuation_db=tx_attenuation_db)
        self.pluto_tx_sink = iio.fmcomms2_sink_fc32(device_uri if device_uri else iio.get_pluto_uri(), [True, True], tx_buffer_samples, False)
        self.pluto_tx_sink.set_len_tag_key('')
        self.pluto_tx_sink.set_bandwidth(rf_bandwidth_hz)
        self.pluto_tx_sink.set_frequency(center_frequency_hz)
        self.pluto_tx_sink.set_samplerate(samp_rate)
        self.pluto_tx_sink.set_attenuation(0, tx_attenuation_db)
        self.pluto_tx_sink.set_filter_params('Auto', '', 0, 0)
        self.placeholder_source = analog.sig_source_c(samp_rate, analog.GR_COS_WAVE, placeholder_frequency_hz, placeholder_amplitude, 0, 0)
        self.contest_tx_source = contest_tx_source.blk(role='sim' if input_mode == 'contest_file' else 'idle', input_path=input_path, manifest_path=tx_manifest_path, modulation=modulation, fec_mode=fec_mode, samp_rate=samp_rate, samples_per_symbol=samples_per_symbol, rolloff=rrc_rolloff, span=rrc_span, block_size=block_size, preamble_symbols=preamble_symbols, guard_symbols=guard_symbols, seed=seed, tx_scale=tx_scale)


        ##################################################
        # Connections
        ##################################################
        self.connect((self.contest_tx_source, 0), (self.tx_input_selector, 1))
        self.connect((self.placeholder_source, 0), (self.tx_input_selector, 0))
        self.connect((self.tx_authorization_gate, 0), (self.pluto_tx_sink, 0))
        self.connect((self.tx_finite_head, 0), (self.tx_authorization_gate, 0))
        self.connect((self.tx_input_selector, 0), (self.tx_finite_head, 0))


    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.set_max_tx_samples(min(int(self.rf_duration_s*self.samp_rate), 10000000))
        self.placeholder_source.set_sampling_freq(self.samp_rate)
        self.contest_tx_source.samp_rate = self.samp_rate
        self.pluto_tx_sink.set_samplerate(self.samp_rate)

    def get_rf_duration_s(self):
        return self.rf_duration_s

    def set_rf_duration_s(self, rf_duration_s):
        self.rf_duration_s = rf_duration_s
        self.set_max_tx_samples(min(int(self.rf_duration_s*self.samp_rate), 10000000))
        self.tx_authorization_gate.rf_duration_s = self.rf_duration_s

    def get_input_mode(self):
        return self.input_mode

    def set_input_mode(self, input_mode):
        self.input_mode = input_mode
        self.set_input_mode_index(0 if self.input_mode == 'placeholder' else 1)
        self.contest_tx_source.role = 'sim' if self.input_mode == 'contest_file' else 'idle'

    def get_tx_scale(self):
        return self.tx_scale

    def set_tx_scale(self, tx_scale):
        self.tx_scale = tx_scale
        self.contest_tx_source.tx_scale = self.tx_scale

    def get_tx_manifest_path(self):
        return self.tx_manifest_path

    def set_tx_manifest_path(self, tx_manifest_path):
        self.tx_manifest_path = tx_manifest_path
        self.contest_tx_source.manifest_path = self.tx_manifest_path

    def get_tx_buffer_samples(self):
        return self.tx_buffer_samples

    def set_tx_buffer_samples(self, tx_buffer_samples):
        self.tx_buffer_samples = tx_buffer_samples

    def get_tx_attenuation_db(self):
        return self.tx_attenuation_db

    def set_tx_attenuation_db(self, tx_attenuation_db):
        self.tx_attenuation_db = tx_attenuation_db
        self.tx_authorization_gate.tx_attenuation_db = self.tx_attenuation_db
        self.pluto_tx_sink.set_attenuation(0,self.tx_attenuation_db)

    def get_seed(self):
        return self.seed

    def set_seed(self, seed):
        self.seed = seed
        self.contest_tx_source.seed = self.seed

    def get_samples_per_symbol(self):
        return self.samples_per_symbol

    def set_samples_per_symbol(self, samples_per_symbol):
        self.samples_per_symbol = samples_per_symbol
        self.contest_tx_source.samples_per_symbol = self.samples_per_symbol

    def get_rules_path(self):
        return self.rules_path

    def set_rules_path(self, rules_path):
        self.rules_path = rules_path
        self.tx_authorization_gate.rules_path = self.rules_path

    def get_rules_confirmed(self):
        return self.rules_confirmed

    def set_rules_confirmed(self, rules_confirmed):
        self.rules_confirmed = rules_confirmed
        self.tx_authorization_gate.rules_confirmed = self.rules_confirmed

    def get_rrc_span(self):
        return self.rrc_span

    def set_rrc_span(self, rrc_span):
        self.rrc_span = rrc_span
        self.contest_tx_source.span = self.rrc_span

    def get_rrc_rolloff(self):
        return self.rrc_rolloff

    def set_rrc_rolloff(self, rrc_rolloff):
        self.rrc_rolloff = rrc_rolloff
        self.contest_tx_source.rolloff = self.rrc_rolloff

    def get_rf_enable(self):
        return self.rf_enable

    def set_rf_enable(self, rf_enable):
        self.rf_enable = rf_enable
        self.tx_authorization_gate.rf_enable = self.rf_enable

    def get_rf_bandwidth_hz(self):
        return self.rf_bandwidth_hz

    def set_rf_bandwidth_hz(self, rf_bandwidth_hz):
        self.rf_bandwidth_hz = rf_bandwidth_hz
        self.tx_authorization_gate.rf_bandwidth_hz = self.rf_bandwidth_hz
        self.pluto_tx_sink.set_bandwidth(self.rf_bandwidth_hz)

    def get_preamble_symbols(self):
        return self.preamble_symbols

    def set_preamble_symbols(self, preamble_symbols):
        self.preamble_symbols = preamble_symbols
        self.contest_tx_source.preamble_symbols = self.preamble_symbols

    def get_placeholder_frequency_hz(self):
        return self.placeholder_frequency_hz

    def set_placeholder_frequency_hz(self, placeholder_frequency_hz):
        self.placeholder_frequency_hz = placeholder_frequency_hz
        self.placeholder_source.set_frequency(self.placeholder_frequency_hz)

    def get_placeholder_amplitude(self):
        return self.placeholder_amplitude

    def set_placeholder_amplitude(self, placeholder_amplitude):
        self.placeholder_amplitude = placeholder_amplitude
        self.placeholder_source.set_amplitude(self.placeholder_amplitude)

    def get_physical_path_confirmed(self):
        return self.physical_path_confirmed

    def set_physical_path_confirmed(self, physical_path_confirmed):
        self.physical_path_confirmed = physical_path_confirmed
        self.tx_authorization_gate.physical_path_confirmed = self.physical_path_confirmed

    def get_modulation(self):
        return self.modulation

    def set_modulation(self, modulation):
        self.modulation = modulation
        self.contest_tx_source.modulation = self.modulation

    def get_max_tx_samples(self):
        return self.max_tx_samples

    def set_max_tx_samples(self, max_tx_samples):
        self.max_tx_samples = max_tx_samples
        self.tx_finite_head.set_length(self.max_tx_samples)

    def get_input_path(self):
        return self.input_path

    def set_input_path(self, input_path):
        self.input_path = input_path
        self.contest_tx_source.input_path = self.input_path

    def get_input_mode_index(self):
        return self.input_mode_index

    def set_input_mode_index(self, input_mode_index):
        self.input_mode_index = input_mode_index
        self.tx_input_selector.set_input_index(self.input_mode_index)

    def get_guard_symbols(self):
        return self.guard_symbols

    def set_guard_symbols(self, guard_symbols):
        self.guard_symbols = guard_symbols
        self.contest_tx_source.guard_symbols = self.guard_symbols

    def get_fec_mode(self):
        return self.fec_mode

    def set_fec_mode(self, fec_mode):
        self.fec_mode = fec_mode
        self.contest_tx_source.fec_mode = self.fec_mode

    def get_device_uri(self):
        return self.device_uri

    def set_device_uri(self, device_uri):
        self.device_uri = device_uri

    def get_center_frequency_hz(self):
        return self.center_frequency_hz

    def set_center_frequency_hz(self, center_frequency_hz):
        self.center_frequency_hz = center_frequency_hz
        self.tx_authorization_gate.center_frequency_hz = self.center_frequency_hz
        self.pluto_tx_sink.set_frequency(self.center_frequency_hz)

    def get_block_size(self):
        return self.block_size

    def set_block_size(self, block_size):
        self.block_size = block_size
        self.contest_tx_source.block_size = self.block_size




def main(top_block_cls=sdr_contest_tx_pluto, options=None):
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
