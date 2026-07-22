"""单文件 GNU Radio Companion 工程的结构和嵌入链路测试。"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np
import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
GRC_DIR = ROOT / "gnu_radio_contest_grc"
GRC_PATH = GRC_DIR / "sdr_contest_complete.grc"
TX_GRC_PATH = GRC_DIR / "sdr_contest_tx_pluto.grc"
RX_GRC_PATH = GRC_DIR / "sdr_contest_rx_pluto.grc"


def _load_grc(path: Path = GRC_PATH) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _embedded_sources(path: Path = GRC_PATH) -> dict[str, str]:
    return {
        block["name"]: block["parameters"]["_source_code"]
        for block in _load_grc(path)["blocks"]
        if block["id"] == "epy_block"
    }


class _SyncBlock:
    """足以加载 EPB 并直接调用其批处理辅助方法的 GNU Radio stub。"""

    def __init__(self, *args, **kwargs):
        self._test_written = 0
        self._test_read = 0
        self._test_tags = []

    def nitems_written(self, _port):
        return self._test_written

    def nitems_read(self, _port):
        return self._test_read

    def add_item_tag(self, _port, offset, key, value):
        self._test_tags.append(types.SimpleNamespace(offset=offset, key=key, value=value))

    def get_tags_in_window(self, *_args, **_kwargs):
        return []


@pytest.fixture()
def gr_stubs(monkeypatch):
    gr_mod = types.ModuleType("gnuradio.gr")
    gr_mod.sync_block = _SyncBlock
    gnuradio_mod = types.ModuleType("gnuradio")
    gnuradio_mod.gr = gr_mod

    pmt_mod = types.ModuleType("pmt")
    pmt_mod.intern = lambda value: value
    pmt_mod.from_long = int
    pmt_mod.to_long = int

    monkeypatch.setitem(sys.modules, "gnuradio", gnuradio_mod)
    monkeypatch.setitem(sys.modules, "gnuradio.gr", gr_mod)
    monkeypatch.setitem(sys.modules, "pmt", pmt_mod)
    return gr_mod, pmt_mod


def _load_epb(name: str, path: Path = GRC_PATH):
    namespace: dict = {}
    source = _embedded_sources(path)[name]
    exec(compile(source, f"{name}.py", "exec"), namespace)
    return namespace["blk"]


def test_split_pluto_graphs_preserve_protocol_and_omit_simulated_channel():
    tx = _load_grc(TX_GRC_PATH)
    rx = _load_grc(RX_GRC_PATH)
    tx_blocks = {block["name"]: block for block in tx["blocks"]}
    rx_blocks = {block["name"]: block for block in rx["blocks"]}

    assert tx["options"]["parameters"]["id"] == "sdr_contest_tx_pluto"
    assert rx["options"]["parameters"]["id"] == "sdr_contest_rx_pluto"
    assert tx["metadata"]["grc_version"] == "3.10.12.0"
    assert rx["metadata"]["grc_version"] == "3.10.12.0"

    assert tx_blocks["placeholder_source"]["id"] == "analog_sig_source_x"
    assert tx_blocks["input_mode"]["parameters"]["value"] == "'placeholder'"
    assert tx_blocks["contest_tx_source"]["id"] == "epy_block"
    assert tx_blocks["tx_finite_head"]["id"] == "blocks_head"
    assert tx_blocks["tx_authorization_gate"]["id"] == "epy_block"
    assert tx_blocks["tx_preflight"]["id"] == "snippet"
    assert tx_blocks["tx_preflight"]["parameters"]["section"] == "init_before_blocks"
    assert "validate_tx_configuration" in tx_blocks["tx_preflight"]["parameters"]["code"]
    assert tx_blocks["pluto_tx_sink"]["id"] == "iio_pluto_sink"
    assert tx_blocks["pluto_tx_sink"]["parameters"]["cyclic"] == "False"
    assert tx_blocks["rf_enable"]["parameters"]["value"] == "False"
    assert tx_blocks["rules_confirmed"]["parameters"]["value"] == "False"
    assert tx_blocks["physical_path_confirmed"]["parameters"]["value"] == "False"

    assert rx_blocks["pluto_rx_source"]["id"] == "iio_pluto_source"
    assert rx_blocks["rx_finite_head"]["id"] == "blocks_head"
    assert rx_blocks["contest_rx_sink"]["id"] == "epy_block"
    assert rx_blocks["contest_rx_sink"]["parameters"]["role"] == "'rx'"
    assert rx_blocks["contest_rx_sink"]["parameters"]["use_frame_tags"] == "False"
    assert rx_blocks["rx_iq_capture"]["id"] == "blocks_file_sink"

    for graph in (tx, rx):
        assert all(block["id"] != "channels_channel_model" for block in graph["blocks"])
        assert "interference_impairments" not in {
            block["name"] for block in graph["blocks"]
        }

    assert ["contest_tx_source", "0", "tx_input_selector", "1"] in tx["connections"]
    assert ["tx_authorization_gate", "0", "pluto_tx_sink", "0"] in tx["connections"]
    assert ["pluto_rx_source", "0", "rx_finite_head", "0"] in rx["connections"]
    assert ["rx_finite_head", "0", "contest_rx_sink", "0"] in rx["connections"]
    assert ["rx_finite_head", "0", "rx_iq_capture", "0"] in rx["connections"]


def test_split_embedded_sources_compile_and_tx_gate_fails_closed(gr_stubs):
    for path in (TX_GRC_PATH, RX_GRC_PATH):
        for name, source in _embedded_sources(path).items():
            compile(source, f"{name}.py", "exec")

    guard_class = _load_epb("tx_authorization_gate", TX_GRC_PATH)
    guard = guard_class(
        rf_enable=False,
        rules_confirmed=False,
        physical_path_confirmed=False,
    )
    with pytest.raises(RuntimeError, match="RF TX gate closed"):
        guard.start()


def test_split_tx_rx_embedded_protocol_is_byte_exact(tmp_path, gr_stubs):
    tx_class = _load_epb("contest_tx_source", TX_GRC_PATH)
    rx_class = _load_epb("contest_rx_sink", RX_GRC_PATH)
    payload = np.random.default_rng(20260721).bytes(777)
    input_path = tmp_path / "competition-input.bin"
    output_path = tmp_path / "decoded-output.bin"
    input_path.write_bytes(payload)

    tx = tx_class(
        role="sim",
        input_path=str(input_path),
        manifest_path=str(tmp_path / "tx-manifest.json"),
        modulation="bpsk",
        fec_mode="convolutional",
        block_size=128,
        samples_per_symbol=8,
        guard_symbols=16,
        seed=42,
    )
    rx = rx_class(
        role="rx",
        output_path=str(output_path),
        metrics_path=str(tmp_path / "rx-metrics.json"),
        modulation="bpsk",
        fec_mode="convolutional",
        samples_per_symbol=8,
        guard_symbols=16,
        seed=42,
    )
    assert tx.start()
    assert rx.start()
    for frame in tx._frames:
        rx._decode_frame(frame)
    assert rx.stop()
    assert output_path.read_bytes() == payload


def test_grc_yaml_graph_and_fail_closed_defaults():
    graph = _load_grc()
    blocks = {block["name"]: block for block in graph["blocks"]}
    assert graph["metadata"]["file_format"] == 1
    assert graph["options"]["parameters"]["output_language"] == "python"
    assert len(graph["connections"]) == 8
    assert sum(block["id"] == "epy_block" for block in graph["blocks"]) == 5
    for required in (
        "contest_tx_source", "channel_model", "interference_impairments",
        "contest_rx_source", "rx_selector", "contest_rx_sink",
        "contest_pluto_tx_sink", "rx_iq_capture",
    ):
        assert required in blocks
    assert blocks["role"]["parameters"]["value"] == "'sim'"
    assert blocks["rf_enable"]["parameters"]["value"] == "False"
    assert blocks["rules_confirmed"]["parameters"]["value"] == "False"
    assert blocks["physical_path_confirmed"]["parameters"]["value"] == "False"
    assert blocks["center_frequency_hz"]["parameters"]["value"] == "0"


def test_all_embedded_python_sources_compile():
    sources = _embedded_sources()
    assert set(sources) == {
        "contest_tx_source", "interference_impairments", "contest_rx_source",
        "contest_rx_sink", "contest_pluto_tx_sink",
    }
    for name, source in sources.items():
        compile(source, f"{name}.py", "exec")


@pytest.mark.parametrize(
    ("modulation", "fec_mode"),
    [
        ("bpsk", "none"),
        ("bpsk", "convolutional"),
        ("qpsk", "none"),
        ("qpsk", "convolutional"),
    ],
)
def test_embedded_file_link_byte_exact(tmp_path, gr_stubs, modulation, fec_mode):
    tx_class = _load_epb("contest_tx_source")
    rx_class = _load_epb("contest_rx_sink")
    payload = np.random.default_rng(2026).bytes(333)
    input_path = tmp_path / "input.bin"
    output_path = tmp_path / "decoded.bin"
    manifest_path = tmp_path / "manifest.json"
    metrics_path = tmp_path / "metrics.json"
    input_path.write_bytes(payload)

    tx = tx_class(
        role="sim", input_path=str(input_path), manifest_path=str(manifest_path),
        modulation=modulation, fec_mode=fec_mode, block_size=128,
        samples_per_symbol=8, guard_symbols=16, seed=7, tx_scale=0.5,
    )
    assert tx.start()
    assert tx._frames

    rx = rx_class(
        role="sim", output_path=str(output_path), metrics_path=str(metrics_path),
        input_path=str(input_path), modulation=modulation, fec_mode=fec_mode,
        samples_per_symbol=8, guard_symbols=16, seed=7,
    )
    assert rx.start()
    for frame in tx._frames:
        rx._decode_frame(frame)
    assert rx.stop()
    assert output_path.read_bytes() == payload
    metrics = yaml.safe_load(metrics_path.read_text(encoding="utf-8"))
    assert metrics["complete"] is True
    assert metrics["byte_exact"] is True
    assert metrics["missing_blocks"] == []


def test_nondefault_guard_is_honored(tmp_path, gr_stubs):
    tx_class = _load_epb("contest_tx_source")
    rx_class = _load_epb("contest_rx_sink")
    payload = b"guard-parameter-regression" * 4
    input_path = tmp_path / "input.bin"
    input_path.write_bytes(payload)
    tx = tx_class(
        role="sim", input_path=str(input_path), manifest_path=str(tmp_path / "m.json"),
        modulation="bpsk", fec_mode="none", block_size=256,
        guard_symbols=24, seed=8,
    )
    assert tx.start()
    rx = rx_class(
        role="sim", output_path=str(tmp_path / "out.bin"),
        metrics_path=str(tmp_path / "metrics.json"), input_path=str(input_path),
        modulation="bpsk", fec_mode="none", guard_symbols=24, seed=8,
    )
    assert rx.start()
    rx._decode_frame(tx._frames[0])
    rx.stop()
    assert (tmp_path / "out.bin").read_bytes() == payload


def test_correlation_fallback_recovers_continuous_iq(tmp_path, gr_stubs):
    """IQ 回放/硬件流没有 frame_len tag 时仍能靠前导相关恢复。"""
    tx_class = _load_epb("contest_tx_source")
    rx_class = _load_epb("contest_rx_sink")
    payload = np.random.default_rng(99).bytes(300)
    input_path = tmp_path / "input.bin"
    input_path.write_bytes(payload)
    tx = tx_class(
        role="sim", input_path=str(input_path), manifest_path=str(tmp_path / "m.json"),
        modulation="bpsk", fec_mode="convolutional", block_size=100,
        guard_symbols=16, seed=9,
    )
    assert tx.start()

    output_path = tmp_path / "out.bin"
    metrics_path = tmp_path / "metrics.json"
    rx = rx_class(
        role="replay", output_path=str(output_path), metrics_path=str(metrics_path),
        input_path=str(input_path), modulation="bpsk", fec_mode="convolutional",
        guard_symbols=16, detection_threshold=0.4, seed=9,
    )
    assert rx.start()
    rx._buffer = np.concatenate(tx._frames)
    rx._scan_and_decode()
    assert rx.stop()
    assert output_path.read_bytes() == payload
    metrics = yaml.safe_load(metrics_path.read_text(encoding="utf-8"))
    assert metrics["correlation_fallback_used"] is True
    assert metrics["accepted_unique_frames"] == 3


def test_public_receiver_recovers_multiple_continuous_frames():
    """公共 Receiver 不再把符号索引误当成采样索引。"""
    from wireless_competition.common.types import FECType, ModulationType, RxProfile
    from wireless_competition.rx.pipeline import Receiver
    from wireless_competition.tx.pipeline import TXPipeline

    payload = np.random.default_rng(100).bytes(300)
    tx = TXPipeline(
        modulation=ModulationType.BPSK, fec_type=FECType.CONVOLUTIONAL,
        block_size=100, seed=10,
    )
    continuous = tx.concat_frames(tx.process_file(payload))
    rx = Receiver(RxProfile(
        modulation=ModulationType.BPSK, fec_type=FECType.CONVOLUTIONAL,
    ))
    results = rx.process(continuous, sample_rate_hz=2.0e6)
    accepted = {
        result.metadata.block_sequence: result.payload_bytes
        for result in results
        if result.payload_crc_pass and result.metadata is not None
    }
    assert b"".join(accepted[index] for index in sorted(accepted)) == payload


def test_pluto_tx_gate_rejects_default_configuration(gr_stubs):
    tx_sink_class = _load_epb("contest_pluto_tx_sink")
    sink = tx_sink_class(
        role="tx", rf_enable=False, rules_confirmed=False,
        physical_path_confirmed=False, center_frequency_hz=0,
    )
    with pytest.raises(RuntimeError, match="RF TX gate closed"):
        sink.start()
