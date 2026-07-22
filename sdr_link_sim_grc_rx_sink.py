import hashlib
import struct
import zlib
from pathlib import Path

import numpy as np
from gnuradio import gr


class blk(gr.sync_block):
    """
    RX Sink: 缓存IQ → 前导互相关帧检测 → 符号定时 → BPSK解调
    → CRC校验 → 写恢复文件
    """

    def __init__(self, output_path="decoded_output.txt",
                 sps=8, alpha=0.35, span=6,
                 preamble_len=64, guard_len=16, seed=42):
        gr.sync_block.__init__(
            self, name="RX Sink", in_sig=[np.complex64], out_sig=None)
        self.output_path = str(output_path)
        self.sps = int(sps)
        self.alpha = float(alpha)
        self.span = int(span)
        self.preamble_len = int(preamble_len)
        self.guard_len = int(guard_len)
        self.seed = int(seed)
        self.sync_word = 0x1ACF
        self._buffer = np.empty(0, dtype=np.complex64)
        self._decoded = False

    # ── helper functions ──
    @staticmethod
    def _rrc_coeffs(spb, a, sp):
        t = np.arange(-sp, sp + 1e-12, 1.0 / spb)
        pi_t = np.pi * t
        f4at = 4.0 * a * t
        denom = pi_t * (1.0 - f4at ** 2)
        numer = np.sin(pi_t * (1.0 - a)) + f4at * np.cos(pi_t * (1.0 + a))
        h = np.zeros_like(t)
        ok = np.abs(denom) >= 1e-12
        h[ok] = numer[ok] / denom[ok]
        idx0 = np.argmin(np.abs(t))
        h[idx0] = 1.0 - a + 4.0 * a / np.pi
        t_sp = 1.0 / (4.0 * a)
        for idx in np.where(np.abs(np.abs(t) - t_sp) < 1e-6)[0]:
            h[idx] = (a / np.sqrt(2.0)) * (
                (1.0 + 2.0 / np.pi) * np.sin(np.pi / (4.0 * a))
                + (1.0 - 2.0 / np.pi) * np.cos(np.pi / (4.0 * a)))
        e = np.sum(np.abs(h) ** 2)
        if e > 0:
            h /= np.sqrt(e)
        return np.float64(h)

    @staticmethod
    def _bpsk_mod(bits):
        return (1.0 - 2.0 * np.asarray(bits, dtype=np.float64)).astype(np.complex128)

    @staticmethod
    def _bpsk_demod(syms):
        return (np.real(syms) < 0).astype(np.uint8)

    @staticmethod
    def _pulse_shape(syms, spb, a, sp):
        rrc = blk._rrc_coeffs(spb, a, sp)
        up = np.zeros(len(syms) * spb, dtype=np.complex128)
        up[::spb] = syms
        return np.convolve(up, rrc)

    @staticmethod
    def _matched_filter(iq, spb, a, sp):
        rrc = blk._rrc_coeffs(spb, a, sp)
        delay = sp * spb
        mf = np.convolve(iq, rrc)
        if len(mf) > 2 * delay:
            mf = mf[delay:-delay]
        return mf

    @staticmethod
    def _preamble_corr(rx_iq, pream_syms, spb, a, sp):
        """归一化前导互相关"""
        p_shaped = blk._pulse_shape(pream_syms, spb, a, sp)
        L = len(p_shaped)
        power = np.abs(rx_iq) ** 2
        cs = np.concatenate([[0.0], np.cumsum(power)])
        win_pwr = cs[L:] - cs[:-L]
        raw = np.abs(np.correlate(rx_iq, p_shaped.conj(), mode="valid"))
        p_eng = np.sum(np.abs(p_shaped) ** 2)
        denom = np.sqrt(win_pwr * p_eng)
        corr = np.zeros(len(rx_iq), dtype=np.float64)
        valid_n = len(raw)
        st = L - 1
        corr[st:st + valid_n] = np.divide(
            raw, denom, out=np.zeros(valid_n, dtype=np.float64),
            where=denom > 1e-12)
        return corr, L

    def _find_frames(self, corr_seq, pshaped_len):
        peak_max = float(np.max(corr_seq))
        if peak_max < 0.40:
            return []
        thr = max(0.40, 0.70 * peak_max)
        L = pshaped_len
        starts = []
        i = 0
        while i < len(corr_seq):
            if corr_seq[i] < thr:
                i += 1
                continue
            j = i
            lim = min(len(corr_seq), i + L)
            pk = i
            while j < lim and corr_seq[j] >= thr:
                if corr_seq[j] > corr_seq[pk]:
                    pk = j
                j += 1
            pream_start = pk - L + 1
            frame_start = max(0, pream_start - self.guard_len * self.sps)
            if not starts or frame_start - starts[-1] > L:
                starts.append(frame_start)
            i = max(j, pk + L // 2)
        return starts

    def _decode_frame(self, rx_iq, frame_iq_start, pream_syms, sync_bits):
        mf = self._matched_filter(rx_iq, self.sps, self.alpha, self.span)
        delay = self.span * self.sps

        # search preamble in MF output near expected position
        approx = frame_iq_start + self.guard_len * self.sps + delay
        win = 2 * delay
        lo = max(0, approx - win)
        hi = min(len(mf) - self.preamble_len * self.sps, approx + win)

        best_offset = approx
        best_phase = 0
        best_c = -1.0
        for off in range(lo, hi):
            for ph in range(self.sps):
                cand = mf[off + ph::self.sps][:self.preamble_len]
                c = float(np.abs(np.dot(cand, pream_syms.conj())))
                if c > best_c:
                    best_c = c
                    best_offset = off
                    best_phase = ph

        pream_iq_start = best_offset + best_phase
        iq_sym0 = pream_iq_start - self.guard_len * self.sps
        while iq_sym0 < 0:
            iq_sym0 += self.sps

        syms_full = mf[iq_sym0::self.sps]
        syms = syms_full[self.guard_len:]
        if len(syms) > self.guard_len:
            syms = syms[:-self.guard_len]

        pos = self.preamble_len

        # sync word
        if pos + 16 > len(syms):
            return None
        rx_sync = self._bpsk_demod(syms[pos:pos + 16])
        pos += 16
        if not np.array_equal(rx_sync, sync_bits):
            return None

        # length
        if pos + 16 > len(syms):
            return None
        rx_len_b = self._bpsk_demod(syms[pos:pos + 16])
        pos += 16
        # bits → bytes
        b_arr = np.asarray(rx_len_b, dtype=np.uint8)
        if len(b_arr) % 8:
            b_arr = np.pad(b_arr, (0, 8 - len(b_arr) % 8))
        rx_len = int.from_bytes(np.packbits(b_arr)[:2], "big")
        if rx_len <= 0 or rx_len > 10_000_000:
            return None

        # payload + crc
        bits_needed = (rx_len + 4) * 8
        if pos + bits_needed > len(syms):
            return None
        rx_b = self._bpsk_demod(syms[pos:pos + bits_needed])
        b_arr2 = np.asarray(rx_b, dtype=np.uint8)
        if len(b_arr2) % 8:
            b_arr2 = np.pad(b_arr2, (0, 8 - len(b_arr2) % 8))
        data_crc = np.packbits(b_arr2).tobytes()
        if len(data_crc) < 4:
            return None
        payload = data_crc[:-4]
        rx_crc = struct.unpack(">I", data_crc[-4:])[0]
        computed = zlib.crc32(payload) & 0xFFFFFFFF
        if computed != rx_crc:
            return None
        return bytes(payload)

    def work(self, input_items, output_items):
        if self._decoded:
            return 0
        x = np.asarray(input_items[0], dtype=np.complex64)
        self._buffer = np.concatenate((self._buffer, x))
        return len(x)

    def stop(self):
        if self._decoded:
            return True
        # 构建前导模板
        rng = np.random.default_rng(self.seed)
        pream_bits = (rng.random(self.preamble_len) > 0.5).astype(np.uint8)
        pream_syms = self._bpsk_mod(pream_bits)

        sync_bits_arr = np.unpackbits(
            np.array([self.sync_word], dtype=">u2").view(np.uint8))

        # 前导互相关
        corr, pshaped_len = self._preamble_corr(
            self._buffer, pream_syms, self.sps, self.alpha, self.span)
        starts = self._find_frames(corr, pshaped_len)

        print(f"[RX-GRC] buffer={len(self._buffer)} samples, "
              f"corr_peak={float(np.max(corr)):.3f}, frames={len(starts)}")

        all_data = bytearray()
        for s in starts:
            result = self._decode_frame(
                self._buffer, s, pream_syms, sync_bits_arr)
            if result is not None:
                all_data.extend(result)
                print(f"[RX-GRC] frame at {s} decoded: {len(result)}B")

        recovered = bytes(all_data)
        target = Path(self.output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_bytes(recovered)
        import os
        os.replace(tmp, target)

        sha = hashlib.sha256(recovered).hexdigest()
        print(f"[RX-GRC] wrote {len(recovered)}B to {target}, SHA256={sha[:16]}...")
        self._decoded = True
        return True
