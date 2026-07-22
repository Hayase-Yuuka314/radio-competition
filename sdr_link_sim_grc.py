#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: SDR Link Full Simulation
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
import sdr_link_sim_grc_rx_sink as rx_sink  # embedded python block
import sdr_link_sim_grc_tx_source as tx_source  # embedded python block
import threading




class sdr_link_sim_grc(gr.top_block):

    def __init__(self):
        gr.top_block.__init__(self, "SDR Link Full Simulation", catch_exceptions=True)
        self.flowgraph_started = threading.Event()

        ##################################################
        # Variables
        ##################################################
        self.snr_db = snr_db = 20.0
        self.sps = sps = 8
        self.span = span = 6
        self.seed = seed = 42
        self.samp_rate = samp_rate = 2000000
        self.preamble_len = preamble_len = 64
        self.output_file = output_file = 'decoded_output.txt'
        self.noise_voltage = noise_voltage = 0.5 * 10**(-snr_db/20.0)
        self.input_file = input_file = 'test_data.txt'
        self.guard_len = guard_len = 16
        self.alpha = alpha = 0.35

        ##################################################
        # Blocks
        ##################################################

        self.tx_source = tx_source.blk(input_path=input_file, sps=sps, alpha=alpha, span=span, preamble_len=preamble_len, guard_len=guard_len, seed=seed)
        self.throttle = blocks.throttle(gr.sizeof_gr_complex*1, samp_rate,False)
        self.rx_sink = rx_sink.blk(output_path=output_file, sps=sps, alpha=alpha, span=span, preamble_len=preamble_len, guard_len=guard_len, seed=seed)
        self.channel_model = channels.channel_model(
            noise_voltage=noise_voltage,
            frequency_offset=0.0,
            epsilon=1.0,
            taps=[1.0+0.0j],
            noise_seed=seed,
            block_tags=False)


        ##################################################
        # Connections
        ##################################################
        self.connect((self.channel_model, 0), (self.rx_sink, 0))
        self.connect((self.throttle, 0), (self.channel_model, 0))
        self.connect((self.tx_source, 0), (self.throttle, 0))


    def get_snr_db(self):
        return self.snr_db

    def set_snr_db(self, snr_db):
        self.snr_db = snr_db
        self.set_noise_voltage(0.5 * 10**(-self.snr_db/20.0))

    def get_sps(self):
        return self.sps

    def set_sps(self, sps):
        self.sps = sps
        self.tx_source.sps = self.sps
        self.rx_sink.sps = self.sps

    def get_span(self):
        return self.span

    def set_span(self, span):
        self.span = span
        self.tx_source.span = self.span
        self.rx_sink.span = self.span

    def get_seed(self):
        return self.seed

    def set_seed(self, seed):
        self.seed = seed
        self.tx_source.seed = self.seed
        self.rx_sink.seed = self.seed

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.throttle.set_sample_rate(self.samp_rate)

    def get_preamble_len(self):
        return self.preamble_len

    def set_preamble_len(self, preamble_len):
        self.preamble_len = preamble_len
        self.tx_source.preamble_len = self.preamble_len
        self.rx_sink.preamble_len = self.preamble_len

    def get_output_file(self):
        return self.output_file

    def set_output_file(self, output_file):
        self.output_file = output_file
        self.rx_sink.output_path = self.output_file

    def get_noise_voltage(self):
        return self.noise_voltage

    def set_noise_voltage(self, noise_voltage):
        self.noise_voltage = noise_voltage
        self.channel_model.set_noise_voltage(self.noise_voltage)

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
        self.rx_sink.guard_len = self.guard_len

    def get_alpha(self):
        return self.alpha

    def set_alpha(self, alpha):
        self.alpha = alpha
        self.tx_source.alpha = self.alpha
        self.rx_sink.alpha = self.alpha




def main(top_block_cls=sdr_link_sim_grc, options=None):
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
