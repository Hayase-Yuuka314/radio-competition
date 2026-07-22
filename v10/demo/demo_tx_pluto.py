#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: Demo TX - DSSS protected text over PlutoSDR
# Author: OpenAI Codex / wireless demo
# Copyright: 2026
# Description: 共享密钥加扰 -> 卷积�?-> 交织 -> BPSK/DSSS -> PlutoSDR
# GNU Radio version: 3.10.12.0

from gnuradio import gr
from gnuradio.filter import firdes
from gnuradio.fft import window
import sys
import signal
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation
from gnuradio import iio
import demo_tx_pluto_demo_tx_source as demo_tx_source  # embedded python block
import threading




class demo_tx_pluto(gr.top_block):

    def __init__(self):
        gr.top_block.__init__(self, "Demo TX - DSSS protected text over PlutoSDR", catch_exceptions=True)
        self.flowgraph_started = threading.Event()

        ##################################################
        # Variables
        ##################################################
        self.tx_buffer_samples = tx_buffer_samples = 32768
        self.tx_attenuation_db = tx_attenuation_db = 60.0
        self.team_id = team_id = 0
        self.shared_key = shared_key = 'demo-shared-key-2026'
        self.sequence = sequence = 1
        self.samples_per_chip = samples_per_chip = 4
        self.samp_rate = samp_rate = 1000000
        self.rf_bandwidth_hz = rf_bandwidth_hz = 800000
        self.message = message = 'el psy kongroo'
        self.manifest_path = manifest_path = 'tx_manifest.json'
        self.gap_samples = gap_samples = 25000
        self.device_uri = device_uri = 'ip:192.168.2.1'
        self.code_length = code_length = 31
        self.center_frequency_hz = center_frequency_hz = 2450000000
        self.baseband_amplitude = baseband_amplitude = 0.25

        ##################################################
        # Blocks
        ##################################################

        self.pluto_tx_sink = iio.fmcomms2_sink_fc32(device_uri if device_uri else iio.get_pluto_uri(), [True, True], tx_buffer_samples, False)
        self.pluto_tx_sink.set_len_tag_key('')
        self.pluto_tx_sink.set_bandwidth(rf_bandwidth_hz)
        self.pluto_tx_sink.set_frequency(center_frequency_hz)
        self.pluto_tx_sink.set_samplerate(samp_rate)
        self.pluto_tx_sink.set_attenuation(0, tx_attenuation_db)
        self.pluto_tx_sink.set_filter_params('Auto', '', 0, 0)
        self.demo_tx_source = demo_tx_source.blk(message=message, shared_key=shared_key, sample_rate=samp_rate, samples_per_chip=samples_per_chip, code_length=code_length, team_id=team_id, amplitude=baseband_amplitude, gap_samples=gap_samples, sequence=sequence, manifest_path=manifest_path)


        ##################################################
        # Connections
        ##################################################
        self.connect((self.demo_tx_source, 0), (self.pluto_tx_sink, 0))


    def get_tx_buffer_samples(self):
        return self.tx_buffer_samples

    def set_tx_buffer_samples(self, tx_buffer_samples):
        self.tx_buffer_samples = tx_buffer_samples

    def get_tx_attenuation_db(self):
        return self.tx_attenuation_db

    def set_tx_attenuation_db(self, tx_attenuation_db):
        self.tx_attenuation_db = tx_attenuation_db
        self.pluto_tx_sink.set_attenuation(0,self.tx_attenuation_db)

    def get_team_id(self):
        return self.team_id

    def set_team_id(self, team_id):
        self.team_id = team_id

    def get_shared_key(self):
        return self.shared_key

    def set_shared_key(self, shared_key):
        self.shared_key = shared_key

    def get_sequence(self):
        return self.sequence

    def set_sequence(self, sequence):
        self.sequence = sequence

    def get_samples_per_chip(self):
        return self.samples_per_chip

    def set_samples_per_chip(self, samples_per_chip):
        self.samples_per_chip = samples_per_chip

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.pluto_tx_sink.set_samplerate(self.samp_rate)

    def get_rf_bandwidth_hz(self):
        return self.rf_bandwidth_hz

    def set_rf_bandwidth_hz(self, rf_bandwidth_hz):
        self.rf_bandwidth_hz = rf_bandwidth_hz
        self.pluto_tx_sink.set_bandwidth(self.rf_bandwidth_hz)

    def get_message(self):
        return self.message

    def set_message(self, message):
        self.message = message

    def get_manifest_path(self):
        return self.manifest_path

    def set_manifest_path(self, manifest_path):
        self.manifest_path = manifest_path

    def get_gap_samples(self):
        return self.gap_samples

    def set_gap_samples(self, gap_samples):
        self.gap_samples = gap_samples

    def get_device_uri(self):
        return self.device_uri

    def set_device_uri(self, device_uri):
        self.device_uri = device_uri

    def get_code_length(self):
        return self.code_length

    def set_code_length(self, code_length):
        self.code_length = code_length

    def get_center_frequency_hz(self):
        return self.center_frequency_hz

    def set_center_frequency_hz(self, center_frequency_hz):
        self.center_frequency_hz = center_frequency_hz
        self.pluto_tx_sink.set_frequency(self.center_frequency_hz)

    def get_baseband_amplitude(self):
        return self.baseband_amplitude

    def set_baseband_amplitude(self, baseband_amplitude):
        self.baseband_amplitude = baseband_amplitude




def main(top_block_cls=demo_tx_pluto, options=None):
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
