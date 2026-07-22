import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pmt
from gnuradio import gr


class blk(gr.sync_block):
    """Tagged fast-path plus correlation fallback receiver and safe reassembler."""

    def __init__(self, role="sim", output_path="decoded_payload.bin",
                 metrics_path="run_metrics.json", input_path="input_payload.bin",
                 modulation="bpsk", fec_mode="convolutional",
                 samp_rate=2000000, samples_per_symbol=8, rolloff=0.35,
                 span=6, preamble_symbols=64, guard_symbols=16,
                 detection_threshold=0.45, max_capture_samples=10000000,
                 use_frame_tags=True, seed=42):
        gr.sync_block.__init__(
            self, name="Contest RX: sync/demod/FEC/CRC/reassembly",
            in_sig=[np.complex64], out_sig=None)
        self.role = str(role)
        self.output_path = str(output_path)
        self.metrics_path = str(metrics_path)
        self.input_path = str(input_path)
        self.modulation = str(modulation).lower()
        self.fec_mode = str(fec_mode).lower()
        self.samp_rate = float(samp_rate)
        self.samples_per_symbol = int(samples_per_symbol)
        self.rolloff = float(rolloff)
        self.span = int(span)
        self.preamble_symbols = int(preamble_symbols)
        self.guard_symbols = int(guard_symbols)
        self.detection_threshold = float(detection_threshold)
        self.max_capture_samples = int(max_capture_samples)
        self.use_frame_tags = bool(use_frame_tags)
        self.seed = int(seed)
        self._buffer = np.empty(0, dtype=np.complex64)
        self._base_abs = 0
        self._pending_tags = []
        self._blocks = {}
        self._total_blocks = None
        self._file_id = None
        self._rx = None
        self._metrics = {}

    def start(self):
        if self.preamble_symbols != 64:
            raise ValueError("protocol v1 requires preamble_symbols=64")
        if self.guard_symbols < 1:
            raise ValueError("guard_symbols must be positive")
        from wireless_competition.common.types import FECType, ModulationType, RxProfile
        from wireless_competition.rx.sim_receiver import SimulationReceiver
        mod_map = {"bpsk": ModulationType.BPSK, "qpsk": ModulationType.QPSK}
        fec_map = {"none": FECType.NONE, "convolutional": FECType.CONVOLUTIONAL}
        if self.modulation not in mod_map or self.fec_mode not in fec_map:
            raise ValueError("unsupported modulation/FEC profile")
        profile = RxProfile(
            modulation=mod_map[self.modulation], fec_type=fec_map[self.fec_mode],
            samples_per_symbol=self.samples_per_symbol,
            rrc_rolloff=self.rolloff, rrc_span=self.span,
            frame_detection_threshold=self.detection_threshold)
        self._rx = SimulationReceiver(profile=profile, seed=self.seed)
        self._buffer = np.empty(0, dtype=np.complex64)
        self._base_abs = 0
        self._pending_tags = []
        self._blocks = {}
        self._total_blocks = None
        self._file_id = None
        self._metrics = {
            "role": self.role, "frames_attempted": 0, "frames_detected": 0,
            "header_failures": 0, "payload_crc_failures": 0,
            "accepted_unique_frames": 0, "duplicate_frames": 0,
            "unique_payload_bytes": 0, "correlation_fallback_used": False,
            "capture_truncated": False}
        return True

    def _decode_frame(self, frame):
        from wireless_competition.common.types import FailureReason
        self._metrics["frames_attempted"] += 1
        result = self._rx.process_frame(
            np.asarray(frame, dtype=np.complex128), self.samp_rate,
            guard_symbols=self.guard_symbols)
        if result.frame_detected:
            self._metrics["frames_detected"] += 1
        reason = getattr(result.failure_reason, "value", str(result.failure_reason))
        if not result.payload_crc_pass or result.metadata is None:
            if "header" in str(reason).lower():
                self._metrics["header_failures"] += 1
            else:
                self._metrics["payload_crc_failures"] += 1
            return
        meta = result.metadata
        seq = int(meta.block_sequence)
        if seq in self._blocks:
            self._metrics["duplicate_frames"] += 1
            return
        self._blocks[seq] = bytes(result.payload_bytes)
        self._total_blocks = int(meta.total_blocks)
        self._file_id = int(meta.file_id)
        self._metrics["accepted_unique_frames"] += 1
        self._metrics["unique_payload_bytes"] += len(result.payload_bytes)

    def _drain_tagged(self):
        self._pending_tags.sort(key=lambda item: item[0])
        while self._pending_tags:
            offset, length = self._pending_tags[0]
            start = int(offset - self._base_abs)
            if start < 0:
                self._pending_tags.pop(0)
                continue
            end = start + int(length)
            if end > len(self._buffer):
                break
            frame = self._buffer[start:end].copy()
            self._decode_frame(frame)
            self._buffer = self._buffer[end:]
            self._base_abs += end
            self._pending_tags.pop(0)

    def work(self, input_items, output_items):
        x = np.asarray(input_items[0], dtype=np.complex64)
        n = len(x)
        absolute = int(self.nitems_read(0))
        tags = (self.get_tags_in_window(0, 0, n, pmt.intern("frame_len"))
                if self.use_frame_tags else [])
        for tag in tags:
            self._pending_tags.append((int(tag.offset), int(pmt.to_long(tag.value))))
        if n:
            room = self.max_capture_samples - len(self._buffer)
            if room <= 0:
                self._metrics["capture_truncated"] = True
            else:
                take = min(n, room)
                self._buffer = np.concatenate((self._buffer, x[:take]))
                if take < n:
                    self._metrics["capture_truncated"] = True
        self._drain_tagged()
        return n

    def _scan_and_decode(self):
        if len(self._buffer) < self.preamble_symbols * self.samples_per_symbol:
            return
        from wireless_competition.rx.detector import FrameDetector
        detector = FrameDetector(
            detection_threshold=self.detection_threshold,
            samples_per_symbol=self.samples_per_symbol,
            preamble_length_symbols=self.preamble_symbols)
        corr = detector.correlate(self._buffer.astype(np.complex128))
        window = len(detector.preamble_shaped)
        peak_max = float(np.max(corr)) if len(corr) else 0.0
        # 绝对门限抑制噪声，相对门限抑制 payload 内偶然出现的次相关峰。
        # 归一化相关使不同接收幅度的合法前导仍可落在同一判据内。
        effective_threshold = max(self.detection_threshold, 0.70 * peak_max)
        candidates = []
        i = 0
        while i < len(corr):
            if corr[i] < effective_threshold:
                i += 1
                continue
            j = i
            limit = min(len(corr), i + window)
            peak = i
            while j < limit and corr[j] >= effective_threshold:
                if corr[j] > corr[peak]:
                    peak = j
                j += 1
            preamble_start = peak - window + 1
            frame_start = max(0, preamble_start - self.guard_symbols * self.samples_per_symbol)
            if not candidates or frame_start - candidates[-1] > window:
                candidates.append(frame_start)
            i = max(j, peak + window // 2)
        if not candidates:
            return
        self._metrics["correlation_fallback_used"] = True
        for index, start in enumerate(candidates):
            end = candidates[index + 1] if index + 1 < len(candidates) else len(self._buffer)
            if end > start:
                self._decode_frame(self._buffer[start:end])

    @staticmethod
    def _atomic_write(path, data):
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, target)

    @staticmethod
    def _atomic_json(path, payload):
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        os.replace(tmp, target)

    def stop(self):
        self._drain_tagged()
        if self._pending_tags or (not self._blocks and len(self._buffer)):
            self._scan_and_decode()
        expected = self._total_blocks
        missing = ([] if expected is None else
                   sorted(set(range(expected)) - set(self._blocks)))
        complete = expected is not None and expected > 0 and not missing
        source = Path(self.input_path)
        if self.role == "sim" and source.is_file() and source.stat().st_size == 0:
            complete = True
            expected = 0
            missing = []
        output_bytes = b""
        if complete:
            output_bytes = b"".join(self._blocks[i] for i in range(expected or 0))
            self._atomic_write(self.output_path, output_bytes)
        elif self._blocks:
            parts_dir = Path(self.output_path + ".parts")
            parts_dir.mkdir(parents=True, exist_ok=True)
            for seq, payload in self._blocks.items():
                self._atomic_write(parts_dir / ("block_%05d.bin" % seq), payload)
        self._metrics.update({
            "file_id": self._file_id, "expected_blocks": expected,
            "missing_blocks": missing, "complete": bool(complete),
            "output_path": str(Path(self.output_path).resolve()) if complete else None,
            "output_sha256": hashlib.sha256(output_bytes).hexdigest() if complete else None,
        })
        if self.role == "sim" and source.is_file():
            original = source.read_bytes()
            self._metrics["input_sha256"] = hashlib.sha256(original).hexdigest()
            self._metrics["byte_exact"] = bool(complete and output_bytes == original)
        self._atomic_json(self.metrics_path, self._metrics)
        print("[contest-rx] complete=%s unique_bytes=%d missing=%s" % (
            complete, self._metrics["unique_payload_bytes"], missing))
        return True
