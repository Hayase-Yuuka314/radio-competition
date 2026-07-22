"""Generate the split PlutoSDR TX/RX GRC projects from the tested PHY blocks.

The generated .grc files are self-contained.  This helper only avoids keeping
three independent copies of the large Embedded Python PHY implementations in
sync while the projects are maintained.
"""

from __future__ import annotations

import copy
from pathlib import Path

import yaml


HERE = Path(__file__).resolve().parent
COMBINED_GRC = HERE / "sdr_contest_complete.grc"
TX_GRC = HERE / "sdr_contest_tx_pluto.grc"
RX_GRC = HERE / "sdr_contest_rx_pluto.grc"


TX_GUARD_SOURCE = r'''from pathlib import Path

import numpy as np
import yaml
from gnuradio import gr


def validate_tx_configuration(rf_enable=False, rules_confirmed=False,
                              physical_path_confirmed=False,
                              rules_path="contest_rules.yaml",
                              center_frequency_hz=2400000000,
                              rf_bandwidth_hz=1000000,
                              rf_duration_s=5.0,
                              tx_attenuation_db=89.75):
    """Validate before the native Pluto sink is constructed or scheduled."""
    if not (bool(rf_enable) and bool(rules_confirmed) and
            bool(physical_path_confirmed)):
        raise RuntimeError(
            "RF TX gate closed: rf_enable, rules_confirmed and "
            "physical_path_confirmed must all be true")
    center_frequency_hz = int(center_frequency_hz)
    rf_bandwidth_hz = int(rf_bandwidth_hz)
    rf_duration_s = float(rf_duration_s)
    tx_attenuation_db = float(tx_attenuation_db)
    if center_frequency_hz <= 0:
        raise RuntimeError("center_frequency_hz must be explicitly set")
    if not (0.0 < rf_duration_s <= 3600.0):
        raise RuntimeError("rf_duration_s must be finite and in (0, 3600]")
    if not (0.0 <= tx_attenuation_db <= 89.75):
        raise RuntimeError("Pluto attenuation must be in [0, 89.75] dB")

    path = Path(str(rules_path))
    if not path.is_file():
        raise RuntimeError("contest rule file not found: %s" % path)
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rules = cfg.get("rules") or {}
    rf = cfg.get("rf") or {}
    if not bool(rules.get("confirmed")):
        raise RuntimeError("contest_rules.yaml rules.confirmed is not true")

    centers = [int(value) for value in
               (rf.get("allowed_center_frequencies_hz") or [])]
    bands = rf.get("allowed_bands_hz") or []
    permitted = center_frequency_hz in centers
    permitted = permitted or any(
        int(low) <= center_frequency_hz <= int(high)
        for low, high in bands)
    if not permitted:
        raise RuntimeError("center frequency is not explicitly authorized")

    max_bw = rf.get("max_occupied_bandwidth_hz")
    if max_bw is None or rf_bandwidth_hz > int(max_bw):
        raise RuntimeError("RF bandwidth is unknown or exceeds constraints")
    max_duration = rules.get("contest_duration_s")
    if max_duration is None or rf_duration_s > float(max_duration):
        raise RuntimeError("TX duration is unknown or exceeds contest duration")
    return True


class blk(gr.sync_block):
    """Fail-closed contest-rule gate placed immediately before PlutoSDR Sink."""

    def __init__(self, rf_enable=False, rules_confirmed=False,
                 physical_path_confirmed=False,
                 rules_path="contest_rules.yaml",
                 center_frequency_hz=2400000000,
                 rf_bandwidth_hz=1000000,
                 rf_duration_s=5.0,
                 tx_attenuation_db=89.75):
        gr.sync_block.__init__(
            self, name="TX authorization gate (fail closed)",
            in_sig=[np.complex64], out_sig=[np.complex64])
        self.rf_enable = bool(rf_enable)
        self.rules_confirmed = bool(rules_confirmed)
        self.physical_path_confirmed = bool(physical_path_confirmed)
        self.rules_path = str(rules_path)
        self.center_frequency_hz = int(center_frequency_hz)
        self.rf_bandwidth_hz = int(rf_bandwidth_hz)
        self.rf_duration_s = float(rf_duration_s)
        self.tx_attenuation_db = float(tx_attenuation_db)

    def start(self):
        return validate_tx_configuration(
            rf_enable=self.rf_enable,
            rules_confirmed=self.rules_confirmed,
            physical_path_confirmed=self.physical_path_confirmed,
            rules_path=self.rules_path,
            center_frequency_hz=self.center_frequency_hz,
            rf_bandwidth_hz=self.rf_bandwidth_hz,
            rf_duration_s=self.rf_duration_s,
            tx_attenuation_db=self.tx_attenuation_db,
        )

    def work(self, input_items, output_items):
        source = input_items[0]
        output_items[0][:len(source)] = source
        return len(source)
'''


def _state(x: float, y: float) -> dict:
    return {
        "bus_sink": False,
        "bus_source": False,
        "bus_structure": None,
        "coordinate": [x, y],
        "rotation": 0,
        "state": "enabled",
    }


def _variable(name: str, value: str, comment: str, x: float, y: float) -> dict:
    return {
        "name": name,
        "id": "variable",
        "parameters": {"comment": comment, "value": value},
        "states": _state(x, y),
    }


def _note(name: str, text: str, x: float, y: float) -> dict:
    return {
        "name": name,
        "id": "note",
        "parameters": {"alias": "", "comment": "", "note": text},
        "states": _state(x, y),
    }


def _block(name: str, block_id: str, parameters: dict,
           x: float, y: float) -> dict:
    return {
        "name": name,
        "id": block_id,
        "parameters": parameters,
        "states": _state(x, y),
    }


def _common_parameters(comment: str = "") -> dict:
    return {
        "affinity": "",
        "alias": "",
        "comment": comment,
        "maxoutbuf": "0",
        "minoutbuf": "0",
    }


def _options(source: dict, graph_id: str, title: str,
             description: str, comment: str) -> dict:
    result = copy.deepcopy(source["options"])
    params = result["parameters"]
    params.update({
        "id": graph_id,
        "title": title,
        "description": description,
        "comment": comment,
        "generate_options": "no_gui",
        "run": "True",
        "run_options": "prompt",
        "window_size": "(1450,900)",
    })
    return result


def _source_block(source: dict, name: str) -> dict:
    return copy.deepcopy(next(block for block in source["blocks"]
                              if block["name"] == name))


def _build_tx(source: dict) -> dict:
    variables = [
        _variable("input_mode", "'placeholder'",
                  "placeholder | contest_file；开赛后切换为 contest_file", 16, 12),
        _variable("input_mode_index", "0 if input_mode == 'placeholder' else 1",
                  "0=默认占位信号，1=竞赛文件协议波形", 216, 12),
        _variable("input_path", "'input_payload.bin'",
                  "开赛后由组委会提供的待发送文件接口", 448, 12),
        _variable("tx_manifest_path", "'tx_manifest.json'",
                  "竞赛文件分帧与哈希清单", 664, 12),
        _variable("placeholder_frequency_hz", "100000.0",
                  "默认复基带占位正弦频率", 888, 12),
        _variable("placeholder_amplitude", "0.10",
                  "占位信号幅度；授权前不会通过 TX 门", 1088, 12),
        _variable("modulation", "'bpsk'", "bpsk | qpsk", 16, 104),
        _variable("fec_mode", "'convolutional'", "none | convolutional", 144, 104),
        _variable("block_size", "256", "竞赛文件分块字节数", 312, 104),
        _variable("samples_per_symbol", "8", "每符号采样数", 440, 104),
        _variable("rrc_rolloff", "0.35", "RRC 滚降系数", 592, 104),
        _variable("rrc_span", "6", "RRC 单侧跨度", 720, 104),
        _variable("preamble_symbols", "64", "协议 v1 固定前导符号数", 832, 104),
        _variable("guard_symbols", "16", "帧首尾保护符号数", 992, 104),
        _variable("seed", "42", "协议确定性种子", 1136, 104),
        _variable("tx_scale", "0.5", "竞赛波形峰值缩放", 1232, 104),
        _variable("device_uri", "'ip:192.168.2.1'",
                  "必须改为已验证的 Pluto/NanoSDR URI", 16, 196),
        _variable("samp_rate", "2000000", "复基带采样率", 224, 196),
        _variable("center_frequency_hz", "2400000000",
                  "示例值；真实 TX 必须同时写入已确认赛规", 352, 196),
        _variable("rf_bandwidth_hz", "1000000", "Pluto TX RF 带宽", 560, 196),
        _variable("tx_buffer_samples", "32768", "Pluto TX 缓冲区样本数", 712, 196),
        _variable("tx_attenuation_db", "89.75",
                  "原生 Pluto 块使用正衰减值；89.75 dB 为最低输出", 880, 196),
        _variable("rf_duration_s", "5.0", "有限发射时长", 1088, 196),
        _variable("max_tx_samples", "min(int(rf_duration_s*samp_rate), 10000000)",
                  "硬上限，禁止无限 TX", 1216, 196),
        _variable("rf_enable", "False", "总 RF 发射开关，默认关闭", 16, 288),
        _variable("rules_confirmed", "False", "完整赛规已确认", 144, 288),
        _variable("physical_path_confirmed", "False",
                  "天线/滤波器/衰减与端口已核对", 304, 288),
        _variable("rules_path", "'contest_rules.yaml'",
                  "授权频率、带宽和时长约束", 528, 288),
    ]

    placeholder = _block("placeholder_source", "analog_sig_source_x", {
        **_common_parameters("默认占位复基带信号；通过 input_mode 切换。"),
        "amp": "placeholder_amplitude",
        "freq": "placeholder_frequency_hz",
        "offset": "0",
        "phase": "0",
        "samp_rate": "samp_rate",
        "showports": "False",
        "type": "complex",
        "waveform": "analog.GR_COS_WAVE",
    }, 24, 508)

    contest_source = _source_block(source, "contest_tx_source")
    contest_source["parameters"]["role"] = (
        "'sim' if input_mode == 'contest_file' else 'idle'")
    contest_source["states"]["coordinate"] = [24, 652]
    contest_source["parameters"]["comment"] = (
        "竞赛文件接口：切换 input_mode='contest_file' 后读取 input_path。")

    selector = _block("tx_input_selector", "blocks_selector", {
        **_common_parameters("0=默认占位源，1=竞赛文件协议源"),
        "enabled": "True",
        "input_index": "input_mode_index",
        "num_inputs": "2",
        "num_outputs": "1",
        "output_index": "0",
        "showports": "True",
        "type": "complex",
        "vlen": "1",
    }, 344, 568)

    head = _block("tx_finite_head", "blocks_head", {
        **_common_parameters("无论输入模式如何，发射样本数均为有限值。"),
        "num_items": "max_tx_samples",
        "type": "complex",
        "vlen": "1",
    }, 568, 568)

    guard = _block("tx_authorization_gate", "epy_block", {
        "_source_code": TX_GUARD_SOURCE,
        **_common_parameters("三重人工确认 + contest_rules.yaml 约束；默认拒绝流。"),
        "center_frequency_hz": "center_frequency_hz",
        "physical_path_confirmed": "physical_path_confirmed",
        "rf_bandwidth_hz": "rf_bandwidth_hz",
        "rf_duration_s": "rf_duration_s",
        "rf_enable": "rf_enable",
        "rules_confirmed": "rules_confirmed",
        "rules_path": "rules_path",
        "tx_attenuation_db": "tx_attenuation_db",
    }, 776, 556)

    preflight = _block("tx_preflight", "snippet", {
        "section": "init_before_blocks",
        "priority": "0",
        "code": (
            "tx_authorization_gate.validate_tx_configuration(\n"
            "    rf_enable=self.rf_enable,\n"
            "    rules_confirmed=self.rules_confirmed,\n"
            "    physical_path_confirmed=self.physical_path_confirmed,\n"
            "    rules_path=self.rules_path,\n"
            "    center_frequency_hz=self.center_frequency_hz,\n"
            "    rf_bandwidth_hz=self.rf_bandwidth_hz,\n"
            "    rf_duration_s=self.rf_duration_s,\n"
            "    tx_attenuation_db=self.tx_attenuation_db,\n"
            ")"
        ),
    }, 1008, 376)

    pluto_sink = _block("pluto_tx_sink", "iio_pluto_sink", {
        **_common_parameters("GNU Radio gr-iio 原生 PlutoSDR Sink；非循环发送。"),
        "attenuation1": "tx_attenuation_db",
        "bandwidth": "rf_bandwidth_hz",
        "buffer_size": "tx_buffer_samples",
        "cyclic": "False",
        "filter": "''",
        "filter_source": "'Auto'",
        "fpass": "0",
        "frequency": "center_frequency_hz",
        "fstop": "0",
        "len_tag_key": "''",
        "samplerate": "samp_rate",
        "type": "fc32",
        "uri": "device_uri",
    }, 1080, 568)

    notes = [
        _note("note_input_interface",
              "默认 input_mode='placeholder' 使用复数正弦占位。开赛后把 input_mode 改为 "
              "'contest_file'，并把 input_path 指向组委会文件；分帧/FEC/调制/RRC 保持不变。",
              24, 388),
        _note("note_tx_safety",
              "真实发射前必须先修复 IIO 设备发现，并确认赛规、频率、带宽、功率、天线/滤波器或有线衰减。"
              "仅当三个布尔门和 contest_rules.yaml 同时通过时才允许样本进入 PlutoSDR Sink；cyclic 永远关闭。",
              720, 376),
    ]

    return {
        "options": _options(
            source, "sdr_contest_tx_pluto", "SDR Contest PlutoSDR Transmitter",
            "占位信号/竞赛文件接口 -> 有限样本与授权门 -> 原生 PlutoSDR Sink",
            "独立发射端。默认占位源且 RF 门关闭；不含仿真信道。"),
        "blocks": variables + [placeholder, contest_source, selector, head,
                                guard, preflight, pluto_sink] + notes,
        "connections": [
            ["placeholder_source", "0", "tx_input_selector", "0"],
            ["contest_tx_source", "0", "tx_input_selector", "1"],
            ["tx_input_selector", "0", "tx_finite_head", "0"],
            ["tx_finite_head", "0", "tx_authorization_gate", "0"],
            ["tx_authorization_gate", "0", "pluto_tx_sink", "0"],
        ],
        "metadata": {"file_format": 1, "grc_version": "3.10.12.0"},
    }


def _build_rx(source: dict) -> dict:
    variables = [
        _variable("device_uri", "'ip:192.168.2.1'",
                  "必须改为已验证的 Pluto/NanoSDR URI", 16, 12),
        _variable("samp_rate", "2000000", "复基带采样率，须与 TX 一致", 224, 12),
        _variable("center_frequency_hz", "2400000000", "接收中心频率", 352, 12),
        _variable("rf_bandwidth_hz", "1000000", "Pluto RX RF 带宽", 536, 12),
        _variable("rf_buffer_samples", "32768", "Pluto RX 缓冲区样本数", 688, 12),
        _variable("rf_duration_s", "5.0", "有限采集时长", 856, 12),
        _variable("max_capture_samples", "10000000", "接收样本硬上限", 984, 12),
        _variable("capture_samples",
                  "min(int(rf_duration_s*samp_rate), max_capture_samples)",
                  "本次实际请求样本数", 1136, 12),
        _variable("rx_gain_mode", "'manual'",
                  "manual | slow_attack | fast_attack | hybrid", 16, 104),
        _variable("rx_gain_db", "30.0", "手动 RX 增益", 176, 104),
        _variable("iq_capture_path", "'rx_capture.c64'",
                  "原始 complex64 IQ 文件", 304, 104),
        _variable("output_path", "'decoded_payload.bin'",
                  "CRC 验证且完整重组后的输出", 496, 104),
        _variable("metrics_path", "'run_metrics.json'",
                  "同步/FEC/CRC/缺块分类指标", 704, 104),
        _variable("input_reference_path", "'input_payload.bin'",
                  "仅离线评分参考，真实 RX 不读取", 896, 104),
        _variable("modulation", "'bpsk'", "须与 TX 一致", 16, 196),
        _variable("fec_mode", "'convolutional'", "须与 TX 一致", 144, 196),
        _variable("samples_per_symbol", "8", "须与 TX 一致", 312, 196),
        _variable("rrc_rolloff", "0.35", "须与 TX 一致", 472, 196),
        _variable("rrc_span", "6", "须与 TX 一致", 600, 196),
        _variable("preamble_symbols", "64", "协议 v1 固定值", 712, 196),
        _variable("guard_symbols", "16", "须与 TX 一致", 872, 196),
        _variable("detection_threshold", "0.45", "归一化前导相关门限", 1016, 196),
        _variable("seed", "42", "协议确定性种子", 1192, 196),
    ]

    pluto_source = _block("pluto_rx_source", "iio_pluto_source", {
        **_common_parameters("GNU Radio gr-iio 原生 PlutoSDR Source。"),
        "bandwidth": "rf_bandwidth_hz",
        "bbdc": "True",
        "buffer_size": "rf_buffer_samples",
        "filter": "''",
        "filter_source": "'Auto'",
        "fpass": "0",
        "frequency": "center_frequency_hz",
        "fstop": "0",
        "gain1": "rx_gain_mode",
        "len_tag_key": "''",
        "manual_gain1": "rx_gain_db",
        "quadrature": "True",
        "rfdc": "True",
        "samplerate": "samp_rate",
        "type": "fc32",
        "uri": "device_uri",
    }, 24, 484)

    head = _block("rx_finite_head", "blocks_head", {
        **_common_parameters("到达时长或样本硬上限后自动结束。"),
        "num_items": "capture_samples",
        "type": "complex",
        "vlen": "1",
    }, 336, 484)

    iq_capture = _block("rx_iq_capture", "blocks_file_sink", {
        "affinity": "",
        "alias": "",
        "append": "False",
        "comment": "原始接收 IQ，complex64 little-endian。",
        "file": "iq_capture_path",
        "type": "complex",
        "unbuffered": "False",
        "vlen": "1",
    }, 664, 636)

    rx_sink = _source_block(source, "contest_rx_sink")
    rx_sink["parameters"].update({
        "role": "'rx'",
        "input_path": "input_reference_path",
        "detection_threshold": "detection_threshold",
        "use_frame_tags": "False",
    })
    rx_sink["parameters"]["comment"] = (
        "连续硬件 IQ 的前导检测、同步、解调、FEC、CRC、去重与安全重组。")
    rx_sink["states"]["coordinate"] = [664, 452]

    notes = [
        _note("note_rx_operation",
              "RX 为有限只读采集：PlutoSDR Source 同时送入原始 IQ 文件和协议接收器。"
              "output_path 只在所有块齐全且 CRC 通过后生成；缺块保存在 .parts 目录。",
              24, 316),
        _note("note_profile_match",
              "center_frequency_hz、samp_rate、modulation、fec_mode、samples_per_symbol、RRC、"
              "前导、保护间隔和 seed 必须与 TX 完全一致。",
              736, 316),
    ]

    return {
        "options": _options(
            source, "sdr_contest_rx_pluto", "SDR Contest PlutoSDR Receiver",
            "原生 PlutoSDR Source -> 有限 IQ 采集 -> 同步/FEC/CRC/去重重组 + IQ 文件",
            "独立接收端。不含仿真信道；保留完整协议解码、原始 IQ 和指标输出。"),
        "blocks": variables + [pluto_source, head, rx_sink, iq_capture] + notes,
        "connections": [
            ["pluto_rx_source", "0", "rx_finite_head", "0"],
            ["rx_finite_head", "0", "contest_rx_sink", "0"],
            ["rx_finite_head", "0", "rx_iq_capture", "0"],
        ],
        "metadata": {"file_format": 1, "grc_version": "3.10.12.0"},
    }


def _write(path: Path, graph: dict) -> None:
    path.write_text(
        yaml.safe_dump(graph, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )


def main() -> int:
    source = yaml.safe_load(COMBINED_GRC.read_text(encoding="utf-8"))
    _write(TX_GRC, _build_tx(source))
    _write(RX_GRC, _build_rx(source))
    print(TX_GRC)
    print(RX_GRC)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
