#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: Not titled yet
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
import sip
import test_contest_rx_sink as contest_rx_sink  # embedded python block
import test_contest_tx_source as contest_tx_source  # embedded python block
import threading



class test(gr.top_block, Qt.QWidget):

    def __init__(self):
        gr.top_block.__init__(self, "Not titled yet", catch_exceptions=True)
        Qt.QWidget.__init__(self)
        self.setWindowTitle("Not titled yet")
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

        self.settings = Qt.QSettings("gnuradio/flowgraphs", "test")

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
        self.capture_seconds = capture_seconds = 30.0
        self.tx_attenuation = tx_attenuation = 30.0
        self.team_id = team_id = 0
        self.shared_key = shared_key = 'contest-key-2026'
        self.samples_per_chip = samples_per_chip = 4
        self.rx_gain = rx_gain = 30.0
        self.rx_buffer_samples = rx_buffer_samples = 32768
        self.rf_bandwidth_0 = rf_bandwidth_0 = 1000000
        self.rf_bandwidth = rf_bandwidth = 1000000
        self.output_dir = output_dir = r'C:\Users\HP\Desktop\radio\radio-competition\v11_contest'
        self.input_file = input_file = 'test_data.txt'
        self.hop_enabled_0 = hop_enabled_0 = 1
        self.hop_enabled = hop_enabled = 1
        self.gap_samples = gap_samples = 50000
        self.device_uri_0 = device_uri_0 = 'usb:1.4.5'
        self.device_uri = device_uri = 'usb:1.4.5'
        self.code_length = code_length = 127
        self.center_freq_0 = center_freq_0 = 2440000000
        self.center_freq = center_freq = 2440000000
        self.capture_samples = capture_samples = int(capture_seconds * samp_rate)
        self.amplitude = amplitude = 0.30

        ##################################################
        # Blocks
        ##################################################

        self.rx_scope = qtgui.time_sink_c(
            1024, #size
            samp_rate, #samp_rate
            "RX Signal", #name
            1, #number of inputs
            None # parent
        )
        self.rx_scope.set_update_time(0.10)
        self.rx_scope.set_y_axis(-0.5, 0.5)

        self.rx_scope.set_y_label('Amplitude', "")

        self.rx_scope.enable_tags(True)
        self.rx_scope.set_trigger_mode(qtgui.TRIG_MODE_FREE, qtgui.TRIG_SLOPE_POS, 0.0, 0, 0, "frame_len")
        self.rx_scope.enable_autoscale(True)
        self.rx_scope.enable_grid(True)
        self.rx_scope.enable_axis_labels(True)
        self.rx_scope.enable_control_panel(False)
        self.rx_scope.enable_stem_plot(False)


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
                    self.rx_scope.set_line_label(i, "Re{{Data {0}}}".format(i/2))
                else:
                    self.rx_scope.set_line_label(i, "Im{{Data {0}}}".format(i/2))
            else:
                self.rx_scope.set_line_label(i, labels[i])
            self.rx_scope.set_line_width(i, widths[i])
            self.rx_scope.set_line_color(i, colors[i])
            self.rx_scope.set_line_style(i, styles[i])
            self.rx_scope.set_line_marker(i, markers[i])
            self.rx_scope.set_line_alpha(i, alphas[i])

        self._rx_scope_win = sip.wrapinstance(self.rx_scope.qwidget(), Qt.QWidget)
        self.top_layout.addWidget(self._rx_scope_win)
        self.pluto_tx_sink = iio.fmcomms2_sink_fc32(device_uri_0 if device_uri_0 else iio.get_pluto_uri(), [True, True], 32768, False)
        self.pluto_tx_sink.set_len_tag_key('')
        self.pluto_tx_sink.set_bandwidth(rf_bandwidth)
        self.pluto_tx_sink.set_frequency(center_freq_0)
        self.pluto_tx_sink.set_samplerate(samp_rate)
        self.pluto_tx_sink.set_attenuation(0, tx_attenuation)
        self.pluto_tx_sink.set_filter_params('Auto', '', 0, 0)
        self.pluto_rx_source = iio.fmcomms2_source_fc32(device_uri if device_uri else iio.get_pluto_uri(), [True, True], rx_buffer_samples)
        self.pluto_rx_source.set_len_tag_key('')
        self.pluto_rx_source.set_frequency(center_freq)
        self.pluto_rx_source.set_samplerate(samp_rate)
        self.pluto_rx_source.set_gain_mode(0, 'manual')
        self.pluto_rx_source.set_gain(0, rx_gain)
        self.pluto_rx_source.set_quadrature(True)
        self.pluto_rx_source.set_rfdc(True)
        self.pluto_rx_source.set_bbdc(True)
        self.pluto_rx_source.set_filter_params('Auto', '', 0, 0)
        self.finite_capture = blocks.head(gr.sizeof_gr_complex*1, capture_samples)
        self.contest_tx_source = contest_tx_source.blk(input_path=input_file, sample_rate=samp_rate, samples_per_chip=samples_per_chip, code_length=code_length, team_id=team_id, shared_key=shared_key, amplitude=amplitude, gap_samples=gap_samples, hop_enabled=hop_enabled)
        self.contest_rx_sink = contest_rx_sink.blk(shared_key=shared_key, sample_rate=samp_rate, samples_per_chip=samples_per_chip, code_length=code_length, team_id=team_id, hop_enabled=hop_enabled, output_dir=output_dir)


        ##################################################
        # Connections
        ##################################################
        self.connect((self.contest_tx_source, 0), (self.pluto_tx_sink, 0))
        self.connect((self.finite_capture, 0), (self.contest_rx_sink, 0))
        self.connect((self.finite_capture, 0), (self.rx_scope, 0))
        self.connect((self.pluto_rx_source, 0), (self.finite_capture, 0))


    def closeEvent(self, event):
        self.settings = Qt.QSettings("gnuradio/flowgraphs", "test")
        self.settings.setValue("geometry", self.saveGeometry())
        self.stop()
        self.wait()

        event.accept()

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.set_capture_samples(int(self.capture_seconds * self.samp_rate))
        self.pluto_rx_source.set_samplerate(self.samp_rate)
        self.pluto_tx_sink.set_samplerate(self.samp_rate)
        self.rx_scope.set_samp_rate(self.samp_rate)

    def get_capture_seconds(self):
        return self.capture_seconds

    def set_capture_seconds(self, capture_seconds):
        self.capture_seconds = capture_seconds
        self.set_capture_samples(int(self.capture_seconds * self.samp_rate))

    def get_tx_attenuation(self):
        return self.tx_attenuation

    def set_tx_attenuation(self, tx_attenuation):
        self.tx_attenuation = tx_attenuation
        self.pluto_tx_sink.set_attenuation(0,self.tx_attenuation)

    def get_team_id(self):
        return self.team_id

    def set_team_id(self, team_id):
        self.team_id = team_id

    def get_shared_key(self):
        return self.shared_key

    def set_shared_key(self, shared_key):
        self.shared_key = shared_key

    def get_samples_per_chip(self):
        return self.samples_per_chip

    def set_samples_per_chip(self, samples_per_chip):
        self.samples_per_chip = samples_per_chip

    def get_rx_gain(self):
        return self.rx_gain

    def set_rx_gain(self, rx_gain):
        self.rx_gain = rx_gain
        self.pluto_rx_source.set_gain(0, self.rx_gain)

    def get_rx_buffer_samples(self):
        return self.rx_buffer_samples

    def set_rx_buffer_samples(self, rx_buffer_samples):
        self.rx_buffer_samples = rx_buffer_samples

    def get_rf_bandwidth_0(self):
        return self.rf_bandwidth_0

    def set_rf_bandwidth_0(self, rf_bandwidth_0):
        self.rf_bandwidth_0 = rf_bandwidth_0

    def get_rf_bandwidth(self):
        return self.rf_bandwidth

    def set_rf_bandwidth(self, rf_bandwidth):
        self.rf_bandwidth = rf_bandwidth
        self.pluto_tx_sink.set_bandwidth(self.rf_bandwidth)

    def get_output_dir(self):
        return self.output_dir

    def set_output_dir(self, output_dir):
        self.output_dir = output_dir
        self.contest_rx_sink.output_dir = self.output_dir

    def get_input_file(self):
        return self.input_file

    def set_input_file(self, input_file):
        self.input_file = input_file
        self.contest_tx_source.input_path = self.input_file

    def get_hop_enabled_0(self):
        return self.hop_enabled_0

    def set_hop_enabled_0(self, hop_enabled_0):
        self.hop_enabled_0 = hop_enabled_0

    def get_hop_enabled(self):
        return self.hop_enabled

    def set_hop_enabled(self, hop_enabled):
        self.hop_enabled = hop_enabled

    def get_gap_samples(self):
        return self.gap_samples

    def set_gap_samples(self, gap_samples):
        self.gap_samples = gap_samples

    def get_device_uri_0(self):
        return self.device_uri_0

    def set_device_uri_0(self, device_uri_0):
        self.device_uri_0 = device_uri_0

    def get_device_uri(self):
        return self.device_uri

    def set_device_uri(self, device_uri):
        self.device_uri = device_uri

    def get_code_length(self):
        return self.code_length

    def set_code_length(self, code_length):
        self.code_length = code_length

    def get_center_freq_0(self):
        return self.center_freq_0

    def set_center_freq_0(self, center_freq_0):
        self.center_freq_0 = center_freq_0
        self.pluto_tx_sink.set_frequency(self.center_freq_0)

    def get_center_freq(self):
        return self.center_freq

    def set_center_freq(self, center_freq):
        self.center_freq = center_freq
        self.pluto_rx_source.set_frequency(self.center_freq)

    def get_capture_samples(self):
        return self.capture_samples

    def set_capture_samples(self, capture_samples):
        self.capture_samples = capture_samples
        self.finite_capture.set_length(self.capture_samples)

    def get_amplitude(self):
        return self.amplitude

    def set_amplitude(self, amplitude):
        self.amplitude = amplitude




def main(top_block_cls=test, options=None):

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
