#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: SDR TX Pluto
# GNU Radio version: 3.10.12.0

from gnuradio import gr
from gnuradio.filter import firdes
from gnuradio.fft import window
import sys
import signal
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation
import sdr_tx_pluto_pluto_tx_sink as pluto_tx_sink  # embedded python block
import sdr_tx_pluto_tx_source as tx_source  # embedded python block
import threading




class sdr_tx_pluto(gr.top_block):

    def __init__(self):
        gr.top_block.__init__(self, "SDR TX Pluto", catch_exceptions=True)
        self.flowgraph_started = threading.Event()

        ##################################################
        # Variables
        ##################################################
        self.tx_scale = tx_scale = 0.5
        self.tx_gain = tx_gain = -10.0
        self.sps = sps = 8
        self.span = span = 6
        self.seed = seed = 42
        self.samp_rate = samp_rate = 2000000
        self.rf_bandwidth = rf_bandwidth = 1000000
        self.preamble_len = preamble_len = 64
        self.input_file = input_file = 'test_data.txt'
        self.guard_len = guard_len = 16
        self.device_uri = device_uri = 'usb:1.5.5'
        self.center_freq = center_freq = 433000000
        self.alpha = alpha = 0.35

        ##################################################
        # Blocks
        ##################################################

        self.tx_source = tx_source.blk(input_path=input_file, sps=sps, alpha=alpha, span=span, preamble_len=preamble_len, guard_len=guard_len, seed=seed, tx_scale=tx_scale)
        self.pluto_tx_sink = pluto_tx_sink.blk(device_uri=device_uri, samp_rate=samp_rate, center_freq=center_freq, rf_bandwidth=rf_bandwidth, tx_gain=tx_gain, tx_scale=tx_scale)


        ##################################################
        # Connections
        ##################################################
        self.connect((self.tx_source, 0), (self.pluto_tx_sink, 0))


    def get_tx_scale(self):
        return self.tx_scale

    def set_tx_scale(self, tx_scale):
        self.tx_scale = tx_scale
        self.pluto_tx_sink.tx_scale = self.tx_scale
        self.tx_source.tx_scale = self.tx_scale

    def get_tx_gain(self):
        return self.tx_gain

    def set_tx_gain(self, tx_gain):
        self.tx_gain = tx_gain
        self.pluto_tx_sink.tx_gain = self.tx_gain

    def get_sps(self):
        return self.sps

    def set_sps(self, sps):
        self.sps = sps
        self.tx_source.sps = self.sps

    def get_span(self):
        return self.span

    def set_span(self, span):
        self.span = span
        self.tx_source.span = self.span

    def get_seed(self):
        return self.seed

    def set_seed(self, seed):
        self.seed = seed
        self.tx_source.seed = self.seed

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.pluto_tx_sink.samp_rate = self.samp_rate

    def get_rf_bandwidth(self):
        return self.rf_bandwidth

    def set_rf_bandwidth(self, rf_bandwidth):
        self.rf_bandwidth = rf_bandwidth
        self.pluto_tx_sink.rf_bandwidth = self.rf_bandwidth

    def get_preamble_len(self):
        return self.preamble_len

    def set_preamble_len(self, preamble_len):
        self.preamble_len = preamble_len
        self.tx_source.preamble_len = self.preamble_len

    def get_input_file(self):
        return self.input_file

    def set_input_file(self, input_file):
        self.input_file = input_file
        self.tx_source.input_path = self.input_file

    def get_guard_len(self):
        return self.guard_len

    def set_guard_len(self, guard_len):
        self.guard_len = guard_len
        self.tx_source.guard_len = self.guard_len

    def get_device_uri(self):
        return self.device_uri

    def set_device_uri(self, device_uri):
        self.device_uri = device_uri
        self.pluto_tx_sink.device_uri = self.device_uri

    def get_center_freq(self):
        return self.center_freq

    def set_center_freq(self, center_freq):
        self.center_freq = center_freq
        self.pluto_tx_sink.center_freq = self.center_freq

    def get_alpha(self):
        return self.alpha

    def set_alpha(self, alpha):
        self.alpha = alpha
        self.tx_source.alpha = self.alpha




def main(top_block_cls=sdr_tx_pluto, options=None):
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
