import json, sys, time
from pathlib import Path
import numpy as np
from gnuradio import gr

for _d in (Path.cwd(), Path.cwd()/"v11_contest",
           Path(r"C:\Users\HP\Desktop\radio\radio-competition\v11_contest")):
    if (_d/"contest_codec.py").is_file() and str(_d) not in sys.path:
        sys.path.insert(0, str(_d))
from contest_codec import (ContestConfig, StreamingDecoder,
                            decode_capture)

class blk(gr.sync_block):
    def __init__(self, shared_key="contest-key-2026", sample_rate=1000000,
                 samples_per_chip=4, code_length=127, team_id=0,
                 hop_enabled=1, output_dir="."):
        gr.sync_block.__init__(self, name="Contest RX Sink",
                               in_sig=[np.complex64], out_sig=None)
        self.config = ContestConfig(
            sample_rate=int(sample_rate),
            samples_per_chip=int(samples_per_chip),
            code_length=int(code_length), team_id=int(team_id),
            shared_key=str(shared_key),
            hop_enabled=bool(int(hop_enabled)))
        self.output_dir = Path(str(output_dir))
        self.decoder = StreamingDecoder(self.config, str(self.output_dir))
        self._buffer = np.empty(0, dtype=np.complex64)
        self._decoded = False
        self._sample_count = 0

    def work(self, input_items, output_items):
        if self._decoded: return 0
        x = np.asarray(input_items[0], dtype=np.complex64).ravel()
        self._buffer = np.concatenate((self._buffer, x))
        self._sample_count += len(x)
        # Print status periodically
        if self._sample_count % 500000 < len(x):
            pwr = 10*np.log10(np.mean(np.abs(x)**2)+1e-20)
            peak = 20*np.log10(np.max(np.abs(x))+1e-20)
            print(f"[RX] buf={len(self._buffer)} count={self._sample_count} "
                  f"pwr={pwr:.1f}dB pk={peak:.1f}dB")
        return len(x)

    def stop(self):
        if self._decoded: return True
        print(f"[RX] captured {len(self._buffer)} samples, decoding...")
        # Normalize
        buf = np.asarray(self._buffer, dtype=np.complex128)
        buf -= np.mean(buf)
        peak = np.max(np.abs(buf))
        if peak > 1e-12: buf /= peak
        buf = buf.astype(np.complex64)

        results = decode_capture(buf, self.config)
        print(f"[RX] packets found: {len(results)}")
        for r in results:
            print(f"  file={r.file_id:08x} seq={r.seq}/{r.total} "
                  f"len={len(r.payload)}B sync={r.sync_score:.3f} "
                  f"cfo={r.cfo_hz:.0f}Hz CRC={'OK' if r.crc_ok else 'FAIL'}")

        # Assemble files
        for fid in set(r.file_id for r in results):
            pkts = sorted([r for r in results if r.file_id == fid],
                          key=lambda r: r.seq)
            total = pkts[0].total if pkts else 0
            received = {r.seq: r.payload for r in pkts}
            complete = len(received) == total and total > 0
            if complete:
                data = b"".join(received[i] for i in range(total))
                import hashlib
                fname = f"decoded_file_{fid:08x}.txt"
                fpath = self.output_dir / fname
                tmp = fpath.with_suffix(fpath.suffix + ".tmp")
                tmp.write_bytes(data)
                import os; os.replace(tmp, fpath)
                sha = hashlib.sha256(data).hexdigest()
                print(f"[RX] COMPLETE: {fname} size={len(data)}B "
                      f"SHA256={sha[:16]}...")
            else:
                missing = sorted(set(range(total)) - set(received.keys()))
                print(f"[RX] partial: file={fid:08x} got={len(received)}/{total}"
                      f" missing={missing[:5]}...")

        # Write status
        status = {
            "packets_found": len(results),
            "unique_packets": len(set((r.file_id, r.seq) for r in results)),
            "files_complete": sum(1 for fid in set(r.file_id for r in results)
                                  if len(set(r.seq for r in results if r.file_id==fid))
                                  == next((r.total for r in results if r.file_id==fid), 0)),
            "config": {
                "code_length": self.config.code_length,
                "processing_gain_db": self.config.processing_gain_db,
                "hop_enabled": self.config.hop_enabled,
                "team_id": self.config.team_id,
            },
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        sfile = self.output_dir / "rx_status.json"
        sfile.write_text(json.dumps(status, ensure_ascii=False, indent=2)+"\n",
                         encoding="utf-8")
        print(f"[RX] status -> {sfile}")
        self._decoded = True
        return True
