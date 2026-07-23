"""
PlutoSDR 回环自测 v2 —— 不依赖 GRC，直接测硬件TX→RX链路

用法:
  TX端: py pluto_loopback_test.py --mode tx --uri usb:1.5.5 --freq 2450000000
  RX端: py pluto_loopback_test.py --mode rx --uri ip:192.168.2.1 --freq 2450000000

先起RX，再起TX。RX控制台会打印实时功率，看到功率跳变说明收到信号。
RX收到信号后 Ctrl+C 停止，自动解码。

依赖: pip install pyadi-iio numpy
"""

import argparse
import struct
import sys
import time
import zlib
from pathlib import Path
import numpy as np

# ── params ──
SPS = 8
ALPHA = 0.35
SPAN = 6
PREAMBLE_LEN = 64
GUARD_LEN = 16
SYNC_WORD = 0x1A_CF
SEED = 42
SAMP_RATE = 2_000_000
RF_BW = 1_000_000
TX_SCALE = 0.5

TEST_DATA = b"SYNCHELLO SDR TEST 1234567890\nLOOPBACK OK!"

# ── DSP ──

def rrc_filter(spb, a, sp):
    t = np.arange(-sp, sp + 1e-12, 1.0 / spb)
    pi_t = np.pi * t; f4at = 4.0 * a * t
    denom = pi_t * (1.0 - f4at ** 2)
    numer = np.sin(pi_t * (1.0 - a)) + f4at * np.cos(pi_t * (1.0 + a))
    h = np.zeros_like(t); ok = np.abs(denom) >= 1e-12
    h[ok] = numer[ok] / denom[ok]
    idx0 = np.argmin(np.abs(t))
    h[idx0] = 1.0 - a + 4.0 * a / np.pi
    tsp = 1.0 / (4.0 * a)
    for idx in np.where(np.abs(np.abs(t) - tsp) < 1e-6)[0]:
        h[idx] = (a / np.sqrt(2.0)) * ((1.0 + 2.0 / np.pi) * np.sin(np.pi / (4.0 * a))
                                        + (1.0 - 2.0 / np.pi) * np.cos(np.pi / (4.0 * a)))
    e = np.sum(np.abs(h) ** 2)
    if e > 0: h /= np.sqrt(e)
    return np.float64(h)

def bpsk_mod(bits):
    return (1.0 - 2.0 * np.asarray(bits, dtype=np.float64)).astype(np.complex128)

def bpsk_demod(syms):
    return (np.real(syms) < 0).astype(np.uint8)

def pulse_shape(syms, spb, a, sp):
    rrc = rrc_filter(spb, a, sp)
    up = np.zeros(len(syms) * spb, dtype=np.complex128)
    up[::spb] = syms
    return np.convolve(up, rrc)

def matched_filter(iq, spb, a, sp):
    rrc = rrc_filter(spb, a, sp)
    delay = sp * spb
    m = np.convolve(iq, rrc)
    if len(m) > 2 * delay: m = m[delay:-delay]
    return m

def build_frame(data):
    crc = zlib.crc32(data) & 0xFFFFFFFF
    payload_crc = data + struct.pack(">I", crc)
    payload_bits = np.unpackbits(np.frombuffer(payload_crc, dtype=np.uint8))
    len_bits = np.unpackbits(np.array([len(data)], dtype=">u2").view(np.uint8))
    sync_bits = np.unpackbits(np.array([SYNC_WORD], dtype=">u2").view(np.uint8))
    guard_syms = np.zeros(GUARD_LEN, dtype=np.complex128)
    rng = np.random.default_rng(SEED)
    pream_bits = (rng.random(PREAMBLE_LEN) > 0.5).astype(np.uint8)
    pream_syms = bpsk_mod(pream_bits)
    syms = np.concatenate([
        guard_syms, pream_syms,
        bpsk_mod(sync_bits), bpsk_mod(len_bits),
        bpsk_mod(payload_bits), guard_syms])
    iq = pulse_shape(syms, SPS, ALPHA, SPAN)
    peak = float(np.max(np.abs(iq)))
    if peak > 0: iq = iq * (TX_SCALE / peak)
    return np.asarray(iq, dtype=np.complex64)

# ── TX ──

def do_tx(uri, freq, tx_gain, loops):
    import adi
    sdr = adi.Pluto(uri=uri)
    sdr.sample_rate = SAMP_RATE
    sdr.tx_lo = freq
    sdr.tx_rf_bandwidth = RF_BW
    sdr.tx_hardwaregain_chan0 = tx_gain
    sdr.tx_cyclic_buffer = False
    sdr.tx(np.zeros(1024, dtype=np.complex64))

    frame = build_frame(TEST_DATA)
    gap = np.zeros(200000, dtype=np.complex64)
    parts = [frame]
    for _ in range(loops - 1 if loops > 0 else 99999):
        parts.extend([gap, frame])
    full = np.concatenate(parts)

    print(f"[TX] uri={uri} freq={freq/1e6:.1f}MHz gain={tx_gain}dB "
          f"frame={len(frame)} loops={loops} total={len(full)} "
          f"({len(full)/SAMP_RATE:.1f}s)")
    print("[TX] sending... Ctrl+C to stop")

    chunk = 32768
    pos = 0
    loop_count = 0
    try:
        while True:
            if loops > 0 and loop_count >= loops:
                break
            end = min(pos + chunk, len(full))
            sdr.tx(full[pos:end])
            pos = end
            if pos >= len(full):
                pos = 0
                loop_count += 1
                if loops > 0:
                    print(f"[TX] loop {loop_count}/{loops}")
    except KeyboardInterrupt:
        pass
    finally:
        sdr.tx_destroy_buffer()
        print("[TX] done")

# ── RX ──

def decode_buffer(buf, freq, rx_gain):
    buf = np.asarray(buf, dtype=np.complex128)
    rm = np.mean(buf); rp = np.max(np.abs(buf))
    print(f"[RX decode] samples={len(buf)} mean={rm:.3f} peak={rp:.3f}")
    buf = buf - rm
    if rp > 1e-12: buf = buf / rp
    buf = np.asarray(buf, dtype=np.complex64)

    rng = np.random.default_rng(SEED)
    pb = (rng.random(PREAMBLE_LEN) > 0.5).astype(np.uint8)
    ps = bpsk_mod(pb)
    sb = np.unpackbits(np.array([SYNC_WORD], dtype=">u2").view(np.uint8))

    p_shaped = pulse_shape(ps, SPS, ALPHA, SPAN)
    L = len(p_shaped)
    pw = np.abs(buf) ** 2
    cs = np.concatenate([[0.0], np.cumsum(pw)])
    wp = cs[L:] - cs[:-L]
    raw = np.abs(np.correlate(buf, p_shaped.conj(), mode="valid"))
    pe = np.sum(np.abs(p_shaped) ** 2)
    denom = np.sqrt(wp * pe)
    corr = np.zeros(len(buf), dtype=np.float64)
    vn = len(raw); st = L - 1
    corr[st:st+vn] = np.divide(raw, denom, out=np.zeros(vn, dtype=np.float64),
                                where=denom > 1e-12)
    cpeak = float(np.max(corr))
    print(f"[RX decode] corr_peak={cpeak:.3f}")

    if cpeak < 0.20:
        print("[RX decode] NO SIGNAL. Check: freq match? antennas? gain?")
        return

    thr = max(0.20, 0.70 * cpeak)
    starts = []; i = 0
    while i < len(corr):
        if corr[i] < thr: i += 1; continue
        j, pk = i, i; lim = min(len(corr), i+L)
        while j < lim and corr[j] >= thr:
            if corr[j] > corr[pk]: pk = j
            j += 1
        fs = max(0, (pk - L + 1) - GUARD_LEN * SPS)
        if not starts or fs - starts[-1] > L: starts.append(fs)
        i = max(j, pk + L//2)

    print(f"[RX decode] frames: {len(starts)}")
    for fs in starts[:3]:
        mf = matched_filter(buf, SPS, ALPHA, SPAN)
        dly = SPAN * SPS
        approx = fs + GUARD_LEN * SPS + dly
        win = 2 * dly
        lo = max(0, approx - win); hi = min(len(mf)-PREAMBLE_LEN*SPS, approx+win)
        bo, bp, bc = approx, 0, -1.0
        for off in range(lo, hi):
            for ph in range(SPS):
                cd = mf[off+ph::SPS][:PREAMBLE_LEN]
                d = float(np.abs(np.dot(cd, ps.conj())))
                if d > bc: bc, bo, bp = d, off, ph
        iq0 = bo + bp - GUARD_LEN * SPS
        while iq0 < 0: iq0 += SPS
        sf = mf[iq0::SPS]; syms = sf[GUARD_LEN:]
        if len(syms) > GUARD_LEN: syms = syms[:-GUARD_LEN]

        pos = PREAMBLE_LEN
        if pos+32 > len(syms): continue
        rs = bpsk_demod(syms[pos:pos+16]); pos += 16
        if not np.array_equal(rs, sb):
            print(f"  frame@{fs}: sync mismatch")
            continue
        lb = bpsk_demod(syms[pos:pos+16]); pos += 16
        ba = np.asarray(lb, dtype=np.uint8)
        if len(ba)%8: ba = np.pad(ba, (0,8-len(ba)%8))
        rl = int.from_bytes(np.packbits(ba)[:2], "big")
        bn = (rl+4)*8
        if pos+bn > len(syms): continue
        rb = bpsk_demod(syms[pos:pos+bn])
        ba2 = np.asarray(rb, dtype=np.uint8)
        if len(ba2)%8: ba2 = np.pad(ba2, (0,8-len(ba2)%8))
        dc = np.packbits(ba2).tobytes()
        pl = dc[:-4]; rc = struct.unpack(">I", dc[-4:])[0]
        if (zlib.crc32(pl)&0xFFFFFFFF) != rc:
            print(f"  frame@{fs}: CRC fail")
            continue
        import hashlib
        print(f"\n  *** SUCCESS! frame@{fs}: {len(pl)} bytes ***")
        print(f"  content: {pl.decode('utf-8','replace')}")
        print(f"  SHA256: {hashlib.sha256(pl).hexdigest()}")
        Path("decoded_test.txt").write_bytes(pl)
        return

def do_rx(uri, freq, rx_gain):
    import adi
    sdr = adi.Pluto(uri=uri)
    sdr.sample_rate = SAMP_RATE
    sdr.rx_lo = freq
    sdr.rx_rf_bandwidth = RF_BW
    sdr.gain_control_mode_chan0 = "manual"
    sdr.rx_hardwaregain_chan0 = rx_gain
    sdr.rx_buffer_size = 32768

    print(f"[RX] uri={uri} freq={freq/1e6:.1f}MHz gain={rx_gain}dB")
    print("[RX] listening... (Ctrl+C to stop & decode)")

    buf = np.empty(0, dtype=np.complex64)
    try:
        while True:
            chunk = np.asarray(sdr.rx(), dtype=np.complex64).reshape(-1)
            pwr = 10 * np.log10(np.mean(np.abs(chunk)**2) + 1e-20)
            buf = np.concatenate([buf, chunk])
            # keep sliding window of last 10M samples
            if len(buf) > 10_000_000:
                buf = buf[-10_000_000:]
            if len(buf) % 2_000_000 < len(chunk):
                print(f"  buf={len(buf)} pwr={pwr:.1f}dB")
    except KeyboardInterrupt:
        pass
    finally:
        sdr = None

    print(f"[RX] stopped. buffer={len(buf)} samples")
    raw_path = Path("rx_capture_test.c64")
    buf.tofile(raw_path)
    print(f"[RX] saved raw IQ to {raw_path}")
    decode_buffer(buf, freq, rx_gain)

# ── main ──

def main():
    parser = argparse.ArgumentParser(description="PlutoSDR loopback test")
    parser.add_argument("--mode", choices=["tx","rx"], required=True,
                        help="tx=发射 rx=接收")
    parser.add_argument("--uri", required=True,
                        help="PlutoSDR URI (如 usb:1.5.5 / ip:192.168.2.1)")
    parser.add_argument("--freq", type=float, default=2450000000,
                        help="中心频率 Hz (默认2.45GHz)")
    parser.add_argument("--tx-gain", type=float, default=-10.0,
                        help="TX增益 dB (默认-10)")
    parser.add_argument("--rx-gain", type=float, default=20.0,
                        help="RX增益 dB (默认20，太高会饱和)")
    parser.add_argument("--loops", type=int, default=200,
                        help="TX重复次数 (0=无限)")
    args = parser.parse_args()

    if args.mode == "tx":
        do_tx(args.uri, int(args.freq), args.tx_gain, args.loops)
    else:
        do_rx(args.uri, int(args.freq), args.rx_gain)

if __name__ == "__main__":
    main()
