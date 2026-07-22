#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: Simple 2-FSK Text TX with PlutoSDR
# Author: OpenAI Codex
# Copyright: 2026
# Description: 反复发�?el psy kongroo；无外部 Python 文件依赖
# GNU Radio version: 3.10.12.0

from PyQt5 import Qt
from gnuradio import qtgui
from gnuradio import blocks
from gnuradio import gr
from gnuradio.filter import firdes
from gnuradio.fft import window
import sys
import signal
from PyQt5 import Qt
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation
from gnuradio import iio
import simple_fsk_tx_pluto_simple_fsk_packet_receiver as simple_fsk_packet_receiver  # embedded python block
import simple_fsk_tx_pluto_simple_fsk_packet_source as simple_fsk_packet_source  # embedded python block
import sip
import threading



class simple_fsk_tx_pluto(gr.top_block, Qt.QWidget):

    def __init__(self):
        gr.top_block.__init__(self, "Simple 2-FSK Text TX with PlutoSDR", catch_exceptions=True)
        Qt.QWidget.__init__(self)
        self.setWindowTitle("Simple 2-FSK Text TX with PlutoSDR")
        qtgui.util.check_set_qss()
        try:
            self.setWindowIcon(Qt.QIcon.fromTheme('gnuradio-grc'))
        except BaseException as exc:
            print(f"Qt GUI: Could not set Icon: {str(exc)}", file=sys.stderr)
        self.top_scroll_layout = Qt.QVBoxLayout()
        self.setLayout(self.top_scroll_layout)
        self.top_scroll = Qt.QScrollArea()
        self.top_scroll.setFrameStyle(Qt.QFrame.NoFrame)
        self.top_scroll_layout.addWidget(self.top_scroll)
        self.top_scroll.setWidgetResizable(True)
        self.top_widget = Qt.QWidget()
        self.top_scroll.setWidget(self.top_widget)
        self.top_layout = Qt.QVBoxLayout(self.top_widget)
        self.top_grid_layout = Qt.QGridLayout()
        self.top_layout.addLayout(self.top_grid_layout)

        self.settings = Qt.QSettings("gnuradio/flowgraphs", "simple_fsk_tx_pluto")

        try:
            geometry = self.settings.value("geometry")
            if geometry:
                self.restoreGeometry(geometry)
        except BaseException as exc:
            print(f"Qt GUI: Could not restore geometry: {str(exc)}", file=sys.stderr)
        self.flowgraph_started = threading.Event()

        ##################################################
        # Variables
        ##################################################
        self.samp_rate = samp_rate = 1000000
        self.capture_seconds = capture_seconds = 15.0
        self.tx_buffer_samples = tx_buffer_samples = 32768
        self.tx_attenuation_db = tx_attenuation_db = 10
        self.samples_per_symbol_0 = samples_per_symbol_0 = 100
        self.samples_per_symbol = samples_per_symbol = 100
        self.samp_rate_0 = samp_rate_0 = 1000000
        self.rx_gain_db = rx_gain_db = 35.0
        self.rx_buffer_samples = rx_buffer_samples = 32768
        self.rf_bandwidth_hz_0 = rf_bandwidth_hz_0 = 800000
        self.rf_bandwidth_hz = rf_bandwidth_hz = 800000
        self.output_text_path = output_text_path = 'received_text.txt'
        self.output_status_path = output_status_path = 'rx_status.json'
        self.message = message = 'ama-10 revives'
        self.gap_samples = gap_samples = 20000
        self.device_uri_0 = device_uri_0 = 'ip:192.168.2.1'
        self.device_uri = device_uri = 'usb:1.3.5'
        self.deviation_hz_0 = deviation_hz_0 = 75000.0
        self.deviation_hz = deviation_hz = 75000.0
        self.center_frequency_hz_0 = center_frequency_hz_0 = 2400000000
        self.center_frequency_hz = center_frequency_hz = 2400000000
        self.capture_samples = capture_samples = int(capture_seconds*samp_rate)
        self.amplitude = amplitude = 0.25

        ##################################################
        # Blocks
        ##################################################

        self.simple_fsk_packet_source = simple_fsk_packet_source.blk(message=message, sample_rate=samp_rate, samples_per_symbol=samples_per_symbol, deviation_hz=deviation_hz, amplitude=amplitude, gap_samples=gap_samples)
        self.simple_fsk_packet_receiver = simple_fsk_packet_receiver.blk(sample_rate=samp_rate, samples_per_symbol=samples_per_symbol, deviation_hz=deviation_hz, output_text_path='C:/Users/86186/Desktop/RXTEXT.txt', output_status_path='C:/Users/86186/Desktop/RXSTATUS.json')
        self.qtgui_time_sink_x_0 = qtgui.time_sink_c(
            1024, #size
            samp_rate, #samp_rate
            "", #name
            1, #number of inputs
            None # parent
        )
        self.qtgui_time_sink_x_0.set_update_time(0.10)
        self.qtgui_time_sink_x_0.set_y_axis(-1, 1)

        self.qtgui_time_sink_x_0.set_y_label('Amplitude', "")

        self.qtgui_time_sink_x_0.enable_tags(True)
        self.qtgui_time_sink_x_0.set_trigger_mode(qtgui.TRIG_MODE_FREE, qtgui.TRIG_SLOPE_POS, 0.0, 0, 0, "")
        self.qtgui_time_sink_x_0.enable_autoscale(False)
        self.qtgui_time_sink_x_0.enable_grid(False)
        self.qtgui_time_sink_x_0.enable_axis_labels(True)
        self.qtgui_time_sink_x_0.enable_control_panel(False)
        self.qtgui_time_sink_x_0.enable_stem_plot(False)


        labels = ['Signal 1', 'Signal 2', 'Signal 3', 'Signal 4', 'Signal 5',
            'Signal 6', 'Signal 7', 'Signal 8', 'Signal 9', 'Signal 10']
        widths = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        colors = ['blue', 'red', 'green', 'black', 'cyan',
            'magenta', 'yellow', 'dark red', 'dark green', 'dark blue']
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0]
        styles = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        markers = [-1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1]


        for i in range(2):
            if len(labels[i]) == 0:
                if (i % 2 == 0):
                    self.qtgui_time_sink_x_0.set_line_label(i, "Re{{Data {0}}}".format(i/2))
                else:
                    self.qtgui_time_sink_x_0.set_line_label(i, "Im{{Data {0}}}".format(i/2))
            else:
                self.qtgui_time_sink_x_0.set_line_label(i, labels[i])
            self.qtgui_time_sink_x_0.set_line_width(i, widths[i])
            self.qtgui_time_sink_x_0.set_line_color(i, colors[i])
            self.qtgui_time_sink_x_0.set_line_style(i, styles[i])
            self.qtgui_time_sink_x_0.set_line_marker(i, markers[i])
            self.qtgui_time_sink_x_0.set_line_alpha(i, alphas[i])

        self._qtgui_time_sink_x_0_win = sip.wrapinstance(self.qtgui_time_sink_x_0.qwidget(), Qt.QWidget)
        self.top_layout.addWidget(self._qtgui_time_sink_x_0_win)
        self.qtgui_freq_sink_x_0 = qtgui.freq_sink_c(
            1024, #size
            window.WIN_BLACKMAN_hARRIS, #wintype
            center_frequency_hz, #fc
            samp_rate, #bw
            "", #name
            1,
            None # parent
        )
        self.qtgui_freq_sink_x_0.set_update_time(0.10)
        self.qtgui_freq_sink_x_0.set_y_axis((-140), 10)
        self.qtgui_freq_sink_x_0.set_y_label('Relative Gain', 'dB')
        self.qtgui_freq_sink_x_0.set_trigger_mode(qtgui.TRIG_MODE_FREE, 0.0, 0, "")
        self.qtgui_freq_sink_x_0.enable_autoscale(False)
        self.qtgui_freq_sink_x_0.enable_grid(False)
        self.qtgui_freq_sink_x_0.set_fft_average(1.0)
        self.qtgui_freq_sink_x_0.enable_axis_labels(True)
        self.qtgui_freq_sink_x_0.enable_control_panel(False)
        self.qtgui_freq_sink_x_0.set_fft_window_normalized(False)



        labels = ['', '', '', '', '',
            '', '', '', '', '']
        widths = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        colors = ["blue", "red", "green", "black", "cyan",
            "magenta", "yellow", "dark red", "dark green", "dark blue"]
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0]

        for i in range(1):
            if len(labels[i]) == 0:
                self.qtgui_freq_sink_x_0.set_line_label(i, "Data {0}".format(i))
            else:
                self.qtgui_freq_sink_x_0.set_line_label(i, labels[i])
            self.qtgui_freq_sink_x_0.set_line_width(i, widths[i])
            self.qtgui_freq_sink_x_0.set_line_color(i, colors[i])
            self.qtgui_freq_sink_x_0.set_line_alpha(i, alphas[i])

        self._qtgui_freq_sink_x_0_win = sip.wrapinstance(self.qtgui_freq_sink_x_0.qwidget(), Qt.QWidget)
        self.top_layout.addWidget(self._qtgui_freq_sink_x_0_win)
        self.pluto_tx_sink = iio.fmcomms2_sink_fc32(device_uri if device_uri else iio.get_pluto_uri(), [True, True], tx_buffer_samples, False)
        self.pluto_tx_sink.set_len_tag_key('')
        self.pluto_tx_sink.set_bandwidth(rf_bandwidth_hz)
        self.pluto_tx_sink.set_frequency(center_frequency_hz)
        self.pluto_tx_sink.set_samplerate(samp_rate)
        self.pluto_tx_sink.set_attenuation(0, tx_attenuation_db)
        self.pluto_tx_sink.set_filter_params('Auto', '', 0, 0)
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
        self.connect((self.pluto_rx_source, 0), (self.qtgui_freq_sink_x_0, 0))
        self.connect((self.pluto_rx_source, 0), (self.qtgui_time_sink_x_0, 0))
        self.connect((self.simple_fsk_packet_source, 0), (self.pluto_tx_sink, 0))


    def closeEvent(self, event):
        self.settings = Qt.QSettings("gnuradio/flowgraphs", "simple_fsk_tx_pluto")
        self.settings.setValue("geometry", self.saveGeometry())
        self.stop()
        self.wait()

        event.accept()

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.set_capture_samples(int(self.capture_seconds*self.samp_rate))
        self.pluto_rx_source.set_samplerate(self.samp_rate)
        self.pluto_tx_sink.set_samplerate(self.samp_rate)
        self.qtgui_freq_sink_x_0.set_frequency_range(self.center_frequency_hz, self.samp_rate)
        self.qtgui_time_sink_x_0.set_samp_rate(self.samp_rate)
        self.simple_fsk_packet_receiver.sample_rate = self.samp_rate
        self.simple_fsk_packet_source.sample_rate = self.samp_rate

    def get_capture_seconds(self):
        return self.capture_seconds

    def set_capture_seconds(self, capture_seconds):
        self.capture_seconds = capture_seconds
        self.set_capture_samples(int(self.capture_seconds*self.samp_rate))

    def get_tx_buffer_samples(self):
        return self.tx_buffer_samples

    def set_tx_buffer_samples(self, tx_buffer_samples):
        self.tx_buffer_samples = tx_buffer_samples

    def get_tx_attenuation_db(self):
        return self.tx_attenuation_db

    def set_tx_attenuation_db(self, tx_attenuation_db):
        self.tx_attenuation_db = tx_attenuation_db
        self.pluto_tx_sink.set_attenuation(0,self.tx_attenuation_db)

    def get_samples_per_symbol_0(self):
        return self.samples_per_symbol_0

    def set_samples_per_symbol_0(self, samples_per_symbol_0):
        self.samples_per_symbol_0 = samples_per_symbol_0

    def get_samples_per_symbol(self):
        return self.samples_per_symbol

    def set_samples_per_symbol(self, samples_per_symbol):
        self.samples_per_symbol = samples_per_symbol
        self.simple_fsk_packet_receiver.samples_per_symbol = self.samples_per_symbol
        self.simple_fsk_packet_source.samples_per_symbol = self.samples_per_symbol

    def get_samp_rate_0(self):
        return self.samp_rate_0

    def set_samp_rate_0(self, samp_rate_0):
        self.samp_rate_0 = samp_rate_0

    def get_rx_gain_db(self):
        return self.rx_gain_db

    def set_rx_gain_db(self, rx_gain_db):
        self.rx_gain_db = rx_gain_db
        self.pluto_rx_source.set_gain(0, self.rx_gain_db)

    def get_rx_buffer_samples(self):
        return self.rx_buffer_samples

    def set_rx_buffer_samples(self, rx_buffer_samples):
        self.rx_buffer_samples = rx_buffer_samples

    def get_rf_bandwidth_hz_0(self):
        return self.rf_bandwidth_hz_0

    def set_rf_bandwidth_hz_0(self, rf_bandwidth_hz_0):
        self.rf_bandwidth_hz_0 = rf_bandwidth_hz_0

    def get_rf_bandwidth_hz(self):
        return self.rf_bandwidth_hz

    def set_rf_bandwidth_hz(self, rf_bandwidth_hz):
        self.rf_bandwidth_hz = rf_bandwidth_hz
        self.pluto_tx_sink.set_bandwidth(self.rf_bandwidth_hz)

    def get_output_text_path(self):
        return self.output_text_path

    def set_output_text_path(self, output_text_path):
        self.output_text_path = output_text_path

    def get_output_status_path(self):
        return self.output_status_path

    def set_output_status_path(self, output_status_path):
        self.output_status_path = output_status_path

    def get_message(self):
        return self.message

    def set_message(self, message):
        self.message = message
        self.simple_fsk_packet_source.message = self.message

    def get_gap_samples(self):
        return self.gap_samples

    def set_gap_samples(self, gap_samples):
        self.gap_samples = gap_samples
        self.simple_fsk_packet_source.gap_samples = self.gap_samples

    def get_device_uri_0(self):
        return self.device_uri_0

    def set_device_uri_0(self, device_uri_0):
        self.device_uri_0 = device_uri_0

    def get_device_uri(self):
        return self.device_uri

    def set_device_uri(self, device_uri):
        self.device_uri = device_uri

    def get_deviation_hz_0(self):
        return self.deviation_hz_0

    def set_deviation_hz_0(self, deviation_hz_0):
        self.deviation_hz_0 = deviation_hz_0

    def get_deviation_hz(self):
        return self.deviation_hz

    def set_deviation_hz(self, deviation_hz):
        self.deviation_hz = deviation_hz
        self.simple_fsk_packet_receiver.deviation_hz = self.deviation_hz
        self.simple_fsk_packet_source.deviation_hz = self.deviation_hz

    def get_center_frequency_hz_0(self):
        return self.center_frequency_hz_0

    def set_center_frequency_hz_0(self, center_frequency_hz_0):
        self.center_frequency_hz_0 = center_frequency_hz_0

    def get_center_frequency_hz(self):
        return self.center_frequency_hz

    def set_center_frequency_hz(self, center_frequency_hz):
        self.center_frequency_hz = center_frequency_hz
        self.pluto_rx_source.set_frequency(self.center_frequency_hz)
        self.pluto_tx_sink.set_frequency(self.center_frequency_hz)
        self.qtgui_freq_sink_x_0.set_frequency_range(self.center_frequency_hz, self.samp_rate)

    def get_capture_samples(self):
        return self.capture_samples

    def set_capture_samples(self, capture_samples):
        self.capture_samples = capture_samples
        self.finite_capture.set_length(self.capture_samples)

    def get_amplitude(self):
        return self.amplitude

    def set_amplitude(self, amplitude):
        self.amplitude = amplitude
        self.simple_fsk_packet_source.amplitude = self.amplitude




def main(top_block_cls=simple_fsk_tx_pluto, options=None):

    qapp = Qt.QApplication(sys.argv)

    tb = top_block_cls()

    tb.start()
    tb.flowgraph_started.set()

    tb.show()

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()

        Qt.QApplication.quit()

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    timer = Qt.QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)

    qapp.exec_()

if __name__ == '__main__':
    main()
