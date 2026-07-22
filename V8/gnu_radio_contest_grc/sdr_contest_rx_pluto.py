#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: SDR Contest PlutoSDR Receiver
# Author: Competition Team
# Copyright: 2026
# Description: 原生 PlutoSDR Source -> 有限 IQ 采集 -> 同步/FEC/CRC/去重重组 + IQ 文件
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
import sdr_contest_rx_pluto_contest_rx_sink as contest_rx_sink  # embedded python block
import threading




class sdr_contest_rx_pluto(gr.top_block):

    def __init__(self):
        gr.top_block.__init__(self, "SDR Contest PlutoSDR Receiver", catch_exceptions=True)
        self.flowgraph_started = threading.Event()

        ##################################################
        # Variables
        ##################################################
        self.samp_rate = samp_rate = 2000000
        self.rf_duration_s = rf_duration_s = 5.0
        self.max_capture_samples = max_capture_samples = 10000000
        self.seed = seed = 42
        self.samples_per_symbol = samples_per_symbol = 8
        self.rx_gain_mode = rx_gain_mode = 'manual'
        self.rx_gain_db = rx_gain_db = 30.0
        self.rrc_span = rrc_span = 6
        self.rrc_rolloff = rrc_rolloff = 0.35
        self.rf_buffer_samples = rf_buffer_samples = 32768
        self.rf_bandwidth_hz = rf_bandwidth_hz = 1000000
        self.preamble_symbols = preamble_symbols = 64
        self.output_path = output_path = 'decoded_payload.bin'
        self.modulation = modulation = 'bpsk'
        self.metrics_path = metrics_path = 'run_metrics.json'
        self.iq_capture_path = iq_capture_path = 'rx_capture.c64'
        self.input_reference_path = input_reference_path = 'input_payload.bin'
        self.guard_symbols = guard_symbols = 16
        self.fec_mode = fec_mode = 'convolutional'
        self.device_uri = device_uri = 'ip:192.168.2.1'
        self.detection_threshold = detection_threshold = 0.45
        self.center_frequency_hz = center_frequency_hz = 2400000000
        self.capture_samples = capture_samples = min(int(rf_duration_s*samp_rate), max_capture_samples)

        ##################################################
        # Blocks
        ##################################################

        self.rx_iq_capture = blocks.file_sink(gr.sizeof_gr_complex*1, iq_capture_path, False)
        self.rx_iq_capture.set_unbuffered(False)
        self.rx_finite_head = blocks.head(gr.sizeof_gr_complex*1, capture_samples)
        self.pluto_rx_source = iio.fmcomms2_source_fc32(device_uri if device_uri else iio.get_pluto_uri(), [True, True], rf_buffer_samples)
        self.pluto_rx_source.set_len_tag_key('')
        self.pluto_rx_source.set_frequency(center_frequency_hz)
        self.pluto_rx_source.set_samplerate(samp_rate)
        self.pluto_rx_source.set_gain_mode(0, 'slow_attack')
        self.pluto_rx_source.set_gain(0, rx_gain_db)
        self.pluto_rx_source.set_quadrature(True)
        self.pluto_rx_source.set_rfdc(True)
        self.pluto_rx_source.set_bbdc(True)
        self.pluto_rx_source.set_filter_params('Auto', '', 0, 0)
        self.contest_rx_sink = contest_rx_sink.blk(role='rx', output_path=output_path, metrics_path=metrics_path, input_path=input_reference_path, modulation=modulation, fec_mode=fec_mode, samp_rate=samp_rate, samples_per_symbol=samples_per_symbol, rolloff=rrc_rolloff, span=rrc_span, preamble_symbols=preamble_symbols, guard_symbols=guard_symbols, detection_threshold=detection_threshold, max_capture_samples=max_capture_samples, use_frame_tags=False, seed=seed)


        ##################################################
        # Connections
        ##################################################
        self.connect((self.pluto_rx_source, 0), (self.rx_finite_head, 0))
        self.connect((self.rx_finite_head, 0), (self.contest_rx_sink, 0))
        self.connect((self.rx_finite_head, 0), (self.rx_iq_capture, 0))


    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.set_capture_samples(min(int(self.rf_duration_s*self.samp_rate), self.max_capture_samples))
        self.pluto_rx_source.set_samplerate(self.samp_rate)
        self.contest_rx_sink.samp_rate = self.samp_rate

    def get_rf_duration_s(self):
        return self.rf_duration_s

    def set_rf_duration_s(self, rf_duration_s):
        self.rf_duration_s = rf_duration_s
        self.set_capture_samples(min(int(self.rf_duration_s*self.samp_rate), self.max_capture_samples))

    def get_max_capture_samples(self):
        return self.max_capture_samples

    def set_max_capture_samples(self, max_capture_samples):
        self.max_capture_samples = max_capture_samples
        self.set_capture_samples(min(int(self.rf_duration_s*self.samp_rate), self.max_capture_samples))
        self.contest_rx_sink.max_capture_samples = self.max_capture_samples

    def get_seed(self):
        return self.seed

    def set_seed(self, seed):
        self.seed = seed
        self.contest_rx_sink.seed = self.seed

    def get_samples_per_symbol(self):
        return self.samples_per_symbol

    def set_samples_per_symbol(self, samples_per_symbol):
        self.samples_per_symbol = samples_per_symbol
        self.contest_rx_sink.samples_per_symbol = self.samples_per_symbol

    def get_rx_gain_mode(self):
        return self.rx_gain_mode

    def set_rx_gain_mode(self, rx_gain_mode):
        self.rx_gain_mode = rx_gain_mode

    def get_rx_gain_db(self):
        return self.rx_gain_db

    def set_rx_gain_db(self, rx_gain_db):
        self.rx_gain_db = rx_gain_db
        self.pluto_rx_source.set_gain(0, self.rx_gain_db)

    def get_rrc_span(self):
        return self.rrc_span

    def set_rrc_span(self, rrc_span):
        self.rrc_span = rrc_span
        self.contest_rx_sink.span = self.rrc_span

    def get_rrc_rolloff(self):
        return self.rrc_rolloff

    def set_rrc_rolloff(self, rrc_rolloff):
        self.rrc_rolloff = rrc_rolloff
        self.contest_rx_sink.rolloff = self.rrc_rolloff

    def get_rf_buffer_samples(self):
        return self.rf_buffer_samples

    def set_rf_buffer_samples(self, rf_buffer_samples):
        self.rf_buffer_samples = rf_buffer_samples

    def get_rf_bandwidth_hz(self):
        return self.rf_bandwidth_hz

    def set_rf_bandwidth_hz(self, rf_bandwidth_hz):
        self.rf_bandwidth_hz = rf_bandwidth_hz

    def get_preamble_symbols(self):
        return self.preamble_symbols

    def set_preamble_symbols(self, preamble_symbols):
        self.preamble_symbols = preamble_symbols
        self.contest_rx_sink.preamble_symbols = self.preamble_symbols

    def get_output_path(self):
        return self.output_path

    def set_output_path(self, output_path):
        self.output_path = output_path
        self.contest_rx_sink.output_path = self.output_path

    def get_modulation(self):
        return self.modulation

    def set_modulation(self, modulation):
        self.modulation = modulation
        self.contest_rx_sink.modulation = self.modulation

    def get_metrics_path(self):
        return self.metrics_path

    def set_metrics_path(self, metrics_path):
        self.metrics_path = metrics_path
        self.contest_rx_sink.metrics_path = self.metrics_path

    def get_iq_capture_path(self):
        return self.iq_capture_path

    def set_iq_capture_path(self, iq_capture_path):
        self.iq_capture_path = iq_capture_path
        self.rx_iq_capture.open(self.iq_capture_path)

    def get_input_reference_path(self):
        return self.input_reference_path

    def set_input_reference_path(self, input_reference_path):
        self.input_reference_path = input_reference_path
        self.contest_rx_sink.input_path = self.input_reference_path

    def get_guard_symbols(self):
        return self.guard_symbols

    def set_guard_symbols(self, guard_symbols):
        self.guard_symbols = guard_symbols
        self.contest_rx_sink.guard_symbols = self.guard_symbols

    def get_fec_mode(self):
        return self.fec_mode

    def set_fec_mode(self, fec_mode):
        self.fec_mode = fec_mode
        self.contest_rx_sink.fec_mode = self.fec_mode

    def get_device_uri(self):
        return self.device_uri

    def set_device_uri(self, device_uri):
        self.device_uri = device_uri

    def get_detection_threshold(self):
        return self.detection_threshold

    def set_detection_threshold(self, detection_threshold):
        self.detection_threshold = detection_threshold
        self.contest_rx_sink.detection_threshold = self.detection_threshold

    def get_center_frequency_hz(self):
        return self.center_frequency_hz

    def set_center_frequency_hz(self, center_frequency_hz):
        self.center_frequency_hz = center_frequency_hz
        self.pluto_rx_source.set_frequency(self.center_frequency_hz)

    def get_capture_samples(self):
        return self.capture_samples

    def set_capture_samples(self, capture_samples):
        self.capture_samples = capture_samples
        self.rx_finite_head.set_length(self.capture_samples)




def main(top_block_cls=sdr_contest_rx_pluto, options=None):
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
