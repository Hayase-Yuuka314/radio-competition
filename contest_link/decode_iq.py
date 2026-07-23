"""Offline decoder — 读取 .c64 IQ 文件，QPSK 解码，输出 00-队名.txt

用法: py decode_iq.py rx_capture.c64 MyTeam
"""
import hashlib, struct, sys, zlib
from pathlib import Path
import numpy as np

PL, SW, RSP, RAL = 64, 0x1ACF, 6, 0.35
SPS = 2
SR = 3_000_000

rng = np.random.default_rng(42)
pb_ = (rng.random(PL) > 0.5).astype(np.uint8)

def _rrc(spb=SPS):
    a, sp = RAL, RSP; t = np.arange(-sp, sp + 1e-12, 1. / spb)
    pt = np.pi * t; f4 = 4 * a * t; d = pt * (1 - f4 ** 2)
    n = np.sin(pt * (1 - a)) + f4 * np.cos(pt * (1 + a))
    h = np.zeros_like(t); ok = np.abs(d) >= 1e-12; h[ok] = n[ok] / d[ok]
    h[np.argmin(np.abs(t))] = 1 - a + 4 * a / np.pi; ts = 1 / (4 * a)
    for idx in np.where(np.abs(np.abs(t) - ts) < 1e-6)[0]:
        h[idx] = (a / np.sqrt(2)) * ((1 + 2 / np.pi) * np.sin(np.pi / (4 * a)) + (1 - 2 / np.pi) * np.cos(np.pi / (4 * a)))
    e = np.sum(np.abs(h) ** 2)
    if e > 0: h /= np.sqrt(e)
    return np.float64(h)

def _qmod(b):
    b = np.asarray(b, dtype=np.uint8).ravel()
    if len(b) % 2: b = np.pad(b, (0, 1))
    I = 1 - 2 * b[0::2].astype(np.float64); Q = 1 - 2 * b[1::2].astype(np.float64)
    return ((I + 1j * Q) / np.sqrt(2)).astype(np.complex128)

def _qdemod(s):
    bits = np.empty(len(s) * 2, dtype=np.uint8)
    bits[0::2] = (np.real(s) < 0).astype(np.uint8)
    bits[1::2] = (np.imag(s) < 0).astype(np.uint8)
    return bits

def _mf(iq):
    r = _rrc(); d = RSP * SPS; m = np.convolve(iq, r)
    if len(m) > 2 * d: m = m[d:-d]
    return m

ps = _qmod(np.repeat(pb_, 2))[:PL]
sb_ = np.unpackbits(np.array([SW], dtype=">u2").view(np.uint8)); sb_sym = _qmod(sb_)[:8]

def decode_all(iq_path, team="MyTeam"):
    raw = np.fromfile(iq_path, dtype=np.complex64)
    print(f"[DECODE] loaded {len(raw)} samples ({len(raw)/SR:.1f}s)")
    # search in 10M-sample sliding windows
    step = 5_000_000; total = len(raw); res = {}; meta = {}; done = set()
    for start in range(0, total - 3000000, step):
        end = min(total, start + 10_000_000)
        win = raw[start:end].astype(np.complex128)
        win -= np.mean(win); pk = np.max(np.abs(win))
        if pk > 1e-12: win /= pk
        win = win.astype(np.complex64)
        print(f"  scanning offset {start}...")
        r = _rrc(); up = np.zeros(PL * SPS, dtype=np.complex128); up[::SPS] = ps
        psh = np.convolve(up, r); L = len(psh)
        if len(win) < L: continue
        raw_c = np.abs(np.correlate(win, psh.conj(), mode="valid"))
        pe = np.sum(np.abs(psh) ** 2); pw = np.abs(win) ** 2
        cs = np.concatenate([[0.], np.cumsum(pw)])
        denom = np.sqrt((cs[L:] - cs[:-L]) * pe)
        corr = np.zeros(len(win)); vn = len(raw_c); st = L - 1
        corr[st:st + vn] = np.divide(raw_c, denom, out=np.zeros(vn), where=denom > 1e-12)
        pm = float(np.max(corr))
        if pm < 0.20: continue
        thr = max(0.20, 0.7 * pm); starts = []; i = 0
        while i < len(corr):
            if corr[i] < thr: i += 1; continue
            j = i; pk = i; lim = min(len(corr), i + L)
            while j < lim and corr[j] >= thr:
                if corr[j] > corr[pk]: pk = j; j += 1
            fs = max(0, pk - L + 1)
            if not starts or fs - starts[-1] > L: starts.append(fs)
            i = max(j, pk + L // 2)
        print(f"    peak={pm:.3f} candidates={len(starts)}")
        for s in starts[:15]:
            # decode one
            m = _mf(win); d = RSP * SPS; ap = s + d
            lo = max(0, ap - 2 * d); hi = min(len(m) - PL * SPS, ap + 2 * d)
            bo, bp, bc = ap, 0, -1.
            for off in range(lo, hi):
                for ph in range(SPS):
                    cd = m[off + ph::SPS][:PL]; dv = float(np.abs(np.dot(cd, ps.conj())))
                    if dv > bc: bc, bo, bp = dv, off, ph
            iq0 = bo + bp
            while iq0 < 0: iq0 += SPS
            sf = m[iq0::SPS]; pos = PL
            if pos + 40 > len(sf): continue
            rs_ = _qdemod(sf[pos:pos + 8])[:16]; pos += 8
            if not np.array_equal(rs_, sb_[:len(rs_)]): continue
            hb = _qdemod(sf[pos:pos + 32])[:64]; pos += 32
            ba = np.asarray(hb, dtype=np.uint8)
            if len(ba) % 8: ba = np.pad(ba, (0, 8 - len(ba) % 8))
            h = np.packbits(ba).tobytes()[:8]
            fid = struct.unpack(">H", h[0:2])[0]; seq = struct.unpack(">H", h[2:4])[0]
            tot = struct.unpack(">H", h[4:6])[0]; pl = struct.unpack(">H", h[6:8])[0]
            if pl == 0 or pl > 100000 or tot == 0: continue
            pb = pl + 4; psym = (pb * 8 + 1) // 2
            if pos + psym > len(sf): continue
            p2 = _qdemod(sf[pos:pos + psym])[:pb * 8]
            ba2 = np.asarray(p2, dtype=np.uint8)
            if len(ba2) % 8: ba2 = np.pad(ba2, (0, 8 - len(ba2) % 8))
            pkt = np.packbits(ba2).tobytes()[:pb]; py = pkt[:pl]
            rc = struct.unpack(">I", pkt[pl:pl + 4])[0]
            if (zlib.crc32(py) & 0xFFFFFFFF) != rc: continue
            k = (fid, seq)
            if k not in res:
                res[k] = py; meta[fid] = tot
                got = sum(1 for kk in res if kk[0] == fid)
                print(f"      fid={fid} seq={seq}/{tot} ({100 * got // tot}%)")
                if fid not in done and got >= tot > 0:
                    rcv = {kk[1]: v for kk, v in res.items() if kk[0] == fid}
                    if len(rcv) == tot:
                        data = b"".join(rcv[i] for i in range(tot))
                        fn = Path(f"{fid:02d}-{team}.txt"); fn.write_bytes(data)
                        sha = hashlib.sha256(data).hexdigest()[:16]
                        print(f"      DONE {fn} {len(data)}B sha256={sha}")
                        done.add(fid)

    if not done:
        print(f"[DECODE] partial: {len(res)} packets")
        for fid in meta:
            g = sum(1 for k in res if k[0] == fid)
            print(f"  file{fid}: {g}/{meta[fid]}")

if __name__ == "__main__":
    iq_file = sys.argv[1] if len(sys.argv) > 1 else "rx_capture.c64"
    team = sys.argv[2] if len(sys.argv) > 2 else "MyTeam"
    decode_all(iq_file, team)
