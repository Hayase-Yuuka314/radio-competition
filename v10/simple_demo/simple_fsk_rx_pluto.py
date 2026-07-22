#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: Simple 2-FSK Text RX with PlutoSDR
# Author: OpenAI Codex
# Copyright: 2026
# Description: 自动找包并将 el psy kongroo 写入文本文件；无外部 Python 文件依赖
# GNU Radio version: 3.10.12.0

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
import simple_fsk_rx_pluto_simple_fsk_packet_receiver as simple_fsk_packet_receiver  # embedded python block
import threading




class simple_fsk_rx_pluto(gr.top_block):

    def __init__(self):
        gr.top_block.__init__(self, "Simple 2-FSK Text RX with PlutoSDR", catch_exceptions=True)
        self.flowgraph_started = threading.Event()

        ##################################################
        # Variables
        ##################################################
        self.samp_rate = samp_rate = 1000000
        self.capture_seconds = capture_seconds = 15.0
        self.samples_per_symbol = samples_per_symbol = 100
        self.rx_gain_db = rx_gain_db = 35.0
        self.rx_buffer_samples = rx_buffer_samples = 32768
        self.rf_bandwidth_hz = rf_bandwidth_hz = 800000
        self.output_text_path = output_text_path = 'received_text.txt'
        self.output_status_path = output_status_path = 'rx_status.json'
        self.device_uri = device_uri = 'usb:1.3.5'
        self.deviation_hz = deviation_hz = 75000.0
        self.center_frequency_hz = center_frequency_hz = 2400000000
        self.capture_samples = capture_samples = int(capture_seconds*samp_rate)

        ##################################################
        # Blocks
        ##################################################

        self.simple_fsk_packet_receiver = simple_fsk_packet_receiver.blk(sample_rate=samp_rate, samples_per_symbol=samples_per_symbol, deviation_hz=deviation_hz, output_text_path='./RXTEXT.txt', output_status_path='./RXSTATUS.json')
        self.pluto_rx_source = iio.fmcomms2_source_fc32(device_uri if device_uri else iio.get_pluto_uri(), [True, True], rx_buffer_samples)
        self.pluto_rx_source.set_len_tag_key('')
        self.pluto_rx_source.set_frequency(center_frequency_hz)
        self.pluto_rx_source.set_samplerate(samp_rate)
        self.pluto_rx_source.set_gain_mode(0, 'manual')
        self.pluto_rx_source.set_gain(0, rx_gain_db)
        self.pluto_rx_source.set_quadrature(True)
        self.pluto_rx_source.set_rfdc(True)
        self.pluto_rx_source.set_bbdc(True)
        self.pluto_rx_source.set_filter_params('Auto', '', 0, 0)
        self.finite_capture = blocks.head(gr.sizeof_gr_complex*1, capture_samples)


        ##################################################
        # Connections
        ##################################################
        self.connect((self.finite_capture, 0), (self.simple_fsk_packet_receiver, 0))
        self.connect((self.pluto_rx_source, 0), (self.finite_capture, 0))


    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.set_capture_samples(int(self.capture_seconds*self.samp_rate))
        self.pluto_rx_source.set_samplerate(self.samp_rate)
        self.simple_fsk_packet_receiver.sample_rate = self.samp_rate

    def get_capture_seconds(self):
        return self.capture_seconds

    def set_capture_seconds(self, capture_seconds):
        self.capture_seconds = capture_seconds
        self.set_capture_samples(int(self.capture_seconds*self.samp_rate))

    def get_samples_per_symbol(self):
        return self.samples_per_symbol

    def set_samples_per_symbol(self, samples_per_symbol):
        self.samples_per_symbol = samples_per_symbol
        self.simple_fsk_packet_receiver.samples_per_symbol = self.samples_per_symbol

    def get_rx_gain_db(self):
        return self.rx_gain_db

    def set_rx_gain_db(self, rx_gain_db):
        self.rx_gain_db = rx_gain_db
        self.pluto_rx_source.set_gain(0, self.rx_gain_db)

    def get_rx_buffer_samples(self):
        return self.rx_buffer_samples

    def set_rx_buffer_samples(self, rx_buffer_samples):
        self.rx_buffer_samples = rx_buffer_samples

    def get_rf_bandwidth_hz(self):
        return self.rf_bandwidth_hz

    def set_rf_bandwidth_hz(self, rf_bandwidth_hz):
        self.rf_bandwidth_hz = rf_bandwidth_hz

    def get_output_text_path(self):
        return self.output_text_path

    def set_output_text_path(self, output_text_path):
        self.output_text_path = output_text_path

    def get_output_status_path(self):
        return self.output_status_path

    def set_output_status_path(self, output_status_path):
        self.output_status_path = output_status_path

    def get_device_uri(self):
        return self.device_uri

    def set_device_uri(self, device_uri):
        self.device_uri = device_uri

    def get_deviation_hz(self):
        return self.deviation_hz

    def set_deviation_hz(self, deviation_hz):
        self.deviation_hz = deviation_hz
        self.simple_fsk_packet_receiver.deviation_hz = self.deviation_hz

    def get_center_frequency_hz(self):
        return self.center_frequency_hz

    def set_center_frequency_hz(self, center_frequency_hz):
        self.center_frequency_hz = center_frequency_hz
        self.pluto_rx_source.set_frequency(self.center_frequency_hz)

    def get_capture_samples(self):
        return self.capture_samples

    def set_capture_samples(self, capture_samples):
        self.capture_samples = capture_samples
        self.finite_capture.set_length(self.capture_samples)




def main(top_block_cls=simple_fsk_rx_pluto, options=None):
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
