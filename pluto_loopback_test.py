"""
PlutoSDR 回环自测 —— 不依赖 GRC，直接测试硬件TX→RX链路

用法1（双设备，TX和RX各一台）:
    py pluto_loopback_test.py --tx-uri usb:1.5.5 --rx-uri ip:192.168.2.1

用法2（两台电脑，一台发一台收）:
    TX端: py pluto_loopback_test.py --mode tx --uri usb:1.5.5
    RX端: py pluto_loopback_test.py --mode rx --uri ip:192.168.2.1

依赖: pip install pyadi-iio numpy
"""

import argparse
import struct
import sys
import time
import zlib
from pathlib import Path

import numpy as np

SPS = 8
ALPHA = 0.35
SPAN = 6
PREAMBLE_LEN = 64
GUARD_LEN = 16
SYNC_WORD = 0x1A_CF
SEED = 42
SAMP_RATE = 2_000_000
CENTER_FREQ = 2_450_000_000  # 2.45GHz, less interference than 433MHz
TX_GAIN = -10.0
RX_GAIN = 20.0
RF_BW = 1_000_000
TX_SCALE = 0.5

TEST_DATA = b"SYNCHELLO SDR TEST 1234567890\nLOOPBACK OK!"

# ── DSP ──────────────────────────────────────────────────

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

# ── TX ───────────────────────────────────────────────────

def do_tx(uri, data, freq, loops):
    import adi
    sdr = adi.Pluto(uri=uri)
    sdr.sample_rate = SAMP_RATE
    sdr.tx_lo = freq
    sdr.tx_rf_bandwidth = RF_BW
    sdr.tx_hardwaregain_chan0 = TX_GAIN
    sdr.tx_cyclic_buffer = False
    sdr.tx(np.zeros(1024, dtype=np.complex64))  # warmup

    frame = build_frame(data)
    gap = np.zeros(200000, dtype=np.complex64)   # 0.1s gap
    full = frame
    for _ in range(loops - 1):
        full = np.concatenate([full, gap, frame])

    print(f"[TX] uri={uri} freq={freq/1e6:.1f}MHz data={len(data)}B "
          f"frame={len(frame)}samps loops={loops} total={len(full)}samps "
          f"({len(full)/SAMP_RATE:.1f}s)")
    print("[TX] sending... (Ctrl+C to stop)")

    # Send in chunks
    chunk = 32768
    pos = 0
    try:
        while True:
            end = min(pos + chunk, len(full))
            sdr.tx(full[pos:end])
            pos = end
            if pos >= len(full):
                if loops == 0:
                    pos = 0  # infinite
                else:
                    pos = 0  # restart loop
    except KeyboardInterrupt:
        pass
    finally:
        sdr.tx_destroy_buffer()
        print("[TX] done")

# ── RX ───────────────────────────────────────────────────

def do_rx(uri, freq, duration):
    import adi
    sdr = adi.Pluto(uri=uri)
    sdr.sample_rate = SAMP_RATE
    sdr.rx_lo = freq
    sdr.rx_rf_bandwidth = RF_BW
    sdr.gain_control_mode_chan0 = "manual"
    sdr.rx_hardwaregain_chan0 = RX_GAIN
    sdr.rx_buffer_size = 32768

    max_samps = int(duration * SAMP_RATE)
    print(f"[RX] uri={uri} freq={freq/1e6:.1f}MHz gain={RX_GAIN}dB "
          f"duration={duration}s ({max_samps} samples)")
    print("[RX] listening...")

    buf = np.empty(max_samps, dtype=np.complex64)
    pos = 0
    while pos < max_samps:
        chunk = np.asarray(sdr.rx(), dtype=np.complex64).reshape(-1)
        n = min(len(chunk), max_samps - pos)
        buf[pos:pos + n] = chunk[:n]
        pos += n
        if pos % 2000000 < len(chunk):  # print every ~1s
            pwr = 10 * np.log10(np.mean(np.abs(chunk) ** 2) + 1e-20)
            print(f"  ... collected {pos}/{max_samps} samples, chunkPower={pwr:.1f}dB")

    print(f"[RX] capture complete: {pos} samples")

    # Save raw IQ
    raw_path = Path("rx_capture_test.c64")
    buf[:pos].tofile(raw_path)
    print(f"[RX] raw IQ saved to {raw_path}")

    # ── Decode ──
    buf = buf[:pos]
    raw_mean = np.mean(buf)
    raw_peak = np.max(np.abs(buf))
    print(f"[RX] raw stats: mean={raw_mean:.3f} peak={raw_peak:.3f}")

    # Normalize
    buf = buf - raw_mean
    if raw_peak > 1e-12:
        buf = buf / raw_peak

    # Generate local preamble
    rng = np.random.default_rng(SEED)
    pream_bits = (rng.random(PREAMBLE_LEN) > 0.5).astype(np.uint8)
    pream_syms = bpsk_mod(pream_bits)
    sync_bits = np.unpackbits(np.array([SYNC_WORD], dtype=">u2").view(np.uint8))

    # Preamble correlation
    p_shaped = pulse_shape(pream_syms, SPS, ALPHA, SPAN)
    L = len(p_shaped)
    pw = np.abs(buf) ** 2
    cs = np.concatenate([[0.0], np.cumsum(pw)])
    wp = cs[L:] - cs[:-L]
    raw = np.abs(np.correlate(buf, p_shaped.conj(), mode="valid"))
    pe = np.sum(np.abs(p_shaped) ** 2)
    denom = np.sqrt(wp * pe)
    corr = np.zeros(len(buf), dtype=np.float64)
    vn = len(raw); st = L - 1
    corr[st:st + vn] = np.divide(raw, denom, out=np.zeros(vn, dtype=np.float64),
                                  where=denom > 1e-12)

    cpeak = float(np.max(corr))
    cidx = int(np.argmax(corr))
    print(f"[RX] preamble correlation: peak={cpeak:.3f} at index={cidx}")

    if cpeak < 0.25:
        print("[RX] *** NO SIGNAL DETECTED ***")
        print("[RX] Possible causes:")
        print("      1. TX not running or on different frequency")
        print("      2. Antennas disconnected")
        print("      3. Gain too low or too high (clipping)")
        print("      4. Distance too far / obstacles")
        print(f"[RX] Try: check freq={freq/1e6:.1f}MHz on both sides")
        return

    # Find frames
    thr = max(0.25, 0.70 * cpeak)
    starts = []; i = 0
    while i < len(corr):
        if corr[i] < thr: i += 1; continue
        j, pk = i, i
        lim = min(len(corr), i + L)
        while j < lim and corr[j] >= thr:
            if corr[j] > corr[pk]: pk = j
            j += 1
        fs = max(0, (pk - L + 1) - GUARD_LEN * SPS)
        if not starts or fs - starts[-1] > L: starts.append(fs)
        i = max(j, pk + L // 2)

    print(f"[RX] frames detected: {len(starts)}")

    for fi, fs in enumerate(starts):
        print(f"\n[RX] --- frame {fi+1} at sample {fs} ---")

        # Decode
        mf = matched_filter(buf, SPS, ALPHA, SPAN)
        delay = SPAN * SPS
        approx = fs + GUARD_LEN * SPS + delay
        win = 2 * delay
        lo = max(0, approx - win)
        hi = min(len(mf) - PREAMBLE_LEN * SPS, approx + win)
        bo, bp, bc = approx, 0, -1.0
        for off in range(lo, hi):
            for ph in range(SPS):
                cd = mf[off + ph::SPS][:PREAMBLE_LEN]
                d = float(np.abs(np.dot(cd, pream_syms.conj())))
                if d > bc: bc, bo, bp = d, off, ph
        iq0 = bo + bp - GUARD_LEN * SPS
        while iq0 < 0: iq0 += SPS
        sf = mf[iq0::SPS]
        syms = sf[GUARD_LEN:]
        if len(syms) > GUARD_LEN: syms = syms[:-GUARD_LEN]

        pos = PREAMBLE_LEN
        if pos + 16 > len(syms):
            print("  error: too short for sync"); continue
        rsync = bpsk_demod(syms[pos:pos+16])
        pos += 16
        if not np.array_equal(rsync, sync_bits):
            print(f"  sync MISMATCH! got={np.packbits(np.pad(rsync,(0,8-len(rsync)%8)))[:2].hex()} expected={SYNC_WORD:04x}")
            print(f"  sync symbols: {np.real(syms[PREAMBLE_LEN:PREAMBLE_LEN+16])}")
            continue
        print("  sync OK")

        if pos + 16 > len(syms):
            print("  error: too short for len"); continue
        lb = bpsk_demod(syms[pos:pos+16]); pos += 16
        ba = np.asarray(lb, dtype=np.uint8)
        if len(ba) % 8: ba = np.pad(ba, (0, 8 - len(ba) % 8))
        rl = int.from_bytes(np.packbits(ba)[:2], "big")
        print(f"  payload length: {rl} bytes")
        if rl <= 0 or rl > 100000: print("  invalid length"); continue

        bn = (rl + 4) * 8
        if pos + bn > len(syms):
            print("  error: too short for payload"); continue
        rb = bpsk_demod(syms[pos:pos+bn])
        ba2 = np.asarray(rb, dtype=np.uint8)
        if len(ba2) % 8: ba2 = np.pad(ba2, (0, 8 - len(ba2) % 8))
        dc = np.packbits(ba2).tobytes()
        pl = dc[:-4]; rc = struct.unpack(">I", dc[-4:])[0]
        cc = zlib.crc32(pl) & 0xFFFFFFFF
        if cc != rc:
            print(f"  CRC FAIL: rx={rc:08x} computed={cc:08x}"); continue
        print(f"  CRC OK!")

        import hashlib
        print(f"  SHA256: {hashlib.sha256(pl).hexdigest()}")
        try:
            print(f"  content: {pl.decode('utf-8','replace')}")
        except: pass

        out = Path("decoded_test.txt")
        out.write_bytes(pl)
        print(f"  wrote {len(pl)}B to {out}")
        print(f"\n  *** SUCCESS! PlutoSDR link works ***")

# ── main ─────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="PlutoSDR loopback test")
    parser.add_argument("--mode", choices=["tx", "rx", "loopback"], default="loopback",
                        help="loopback=同一台电脑TX+RX")
    parser.add_argument("--tx-uri", default="ip:192.168.2.1",
                        help="TX Pluto URI")
    parser.add_argument("--rx-uri", default="ip:192.168.2.1",
                        help="RX Pluto URI (loopback模式下可与TX不同)")
    parser.add_argument("--freq", type=float, default=CENTER_FREQ,
                        help="中心频率 Hz")
    parser.add_argument("--duration", type=float, default=10.0,
                        help="RX监听时长 秒 (rx/loopback模式)")
    parser.add_argument("--loops", type=int, default=200,
                        help="TX重复发送次数 (0=无限)")
    parser.add_argument("--rx-gain", type=float, default=RX_GAIN,
                        help="RX增益 dB")
    parser.add_argument("--tx-gain", type=float, default=TX_GAIN,
                        help="TX增益 dB")
    args = parser.parse_args()

    if args.mode == "tx":
        do_tx(args.tx_uri, TEST_DATA, int(args.freq), args.loops)

    elif args.mode == "rx":
        do_rx(args.rx_uri, int(args.freq), args.duration)

    else:  # loopback
        print("=" * 60)
        print("  PlutoSDR Loopback Test")
        print(f"  TX URI: {args.tx_uri}")
        print(f"  RX URI: {args.rx_uri}")
        print(f"  Freq:   {args.freq/1e6:.1f} MHz")
        print(f"  Prefer 2.45GHz for this test (less interference than 433MHz)!")
        print("=" * 60)

        # Start RX in a thread
        import threading
        rx_buf = [None]
        rx_done = threading.Event()

        def rx_thread():
            import adi
            try:
                sdr = adi.Pluto(uri=args.rx_uri)
                sdr.sample_rate = SAMP_RATE
                sdr.rx_lo = int(args.freq)
                sdr.rx_rf_bandwidth = RF_BW
                sdr.gain_control_mode_chan0 = "manual"
                sdr.rx_hardwaregain_chan0 = args.rx_gain
                sdr.rx_buffer_size = 32768
                max_samps = int(args.duration * SAMP_RATE)
                buf = np.empty(max_samps, dtype=np.complex64)
                pos = 0
                while pos < max_samps:
                    chunk = np.asarray(sdr.rx(), dtype=np.complex64).reshape(-1)
                    n = min(len(chunk), max_samps - pos)
                    buf[pos:pos + n] = chunk[:n]
                    pos += n
                rx_buf[0] = buf[:pos]
            except Exception as e:
                print(f"[RX Thread] ERROR: {e}")
            rx_done.set()

        rt = threading.Thread(target=rx_thread, daemon=True)
        rt.start()
        time.sleep(2)  # give RX time to init

        # TX
        print("[TX] Starting transmission...")
        import adi
        tx_sdr = adi.Pluto(uri=args.tx_uri)
        tx_sdr.sample_rate = SAMP_RATE
        tx_sdr.tx_lo = int(args.freq)
        tx_sdr.tx_rf_bandwidth = RF_BW
        tx_sdr.tx_hardwaregain_chan0 = args.tx_gain
        tx_sdr.tx_cyclic_buffer = False
        tx_sdr.tx(np.zeros(1024, dtype=np.complex64))

        frame = build_frame(TEST_DATA)
        gap = np.zeros(200000, dtype=np.complex64)
        full = frame
        for _ in range(args.loops - 1):
            full = np.concatenate([full, gap, frame])
        print(f"[TX] frame={len(frame)} samples, total={len(full)} "
              f"({len(full)/SAMP_RATE:.1f}s)")

        # Send all at once (looping internally)
        chunk = 32768
        pos = 0
        loops_done = 0
        while loops_done < min(3, args.loops):  # send at least 3 loops
            end = min(pos + chunk, len(full))
            tx_sdr.tx(full[pos:end])
            pos = end
            if pos >= len(full):
                pos = 0; loops_done += 1
                print(f"[TX] loop {loops_done} done")

        tx_sdr.tx_destroy_buffer()
        print("[TX] transmission complete")

        # Wait for RX to finish
        rx_done.wait(timeout=30)
        if rx_buf[0] is None:
            print("[RX] *** No data captured! RX thread may have failed ***")
            return

        buf = rx_buf[0]
        print(f"[RX] captured {len(buf)} samples")

        # Normalize and decode (same logic as do_rx)
        rm = np.mean(buf); rp = np.max(np.abs(buf))
        print(f"[RX] raw: mean={rm:.3f} peak={rp:.3f}")
        buf = buf - rm
        if rp > 1e-12: buf = buf / rp

        rng = np.random.default_rng(SEED)
        pb = (rng.random(PREAMBLE_LEN) > 0.5).astype(np.uint8)
        ps = bpsk_mod(pb)
        sb = np.unpackbits(np.array([SYNC_WORD], dtype=">u2").view(np.uint8))

        p_shaped = pulse_shape(ps, SPS, ALPHA, SPAN)
        L = len(p_shaped)
        pw = np.abs(buf) ** 2
        cs = np.concatenate([[0.0], np.cumsum(pw)])
        wp = cs[L:] - cs[:-L]
        raw_c = np.abs(np.correlate(buf, p_shaped.conj(), mode="valid"))
        denom_c = np.sqrt(wp * np.sum(np.abs(p_shaped) ** 2))
        corr_c = np.zeros(len(buf)); vn = len(raw_c); st = L - 1
        corr_c[st:st+vn] = np.divide(raw_c, denom_c,
            out=np.zeros(vn, dtype=np.float64), where=denom_c > 1e-12)
        cpeak_c = float(np.max(corr_c))
        print(f"[RX] corr_peak={cpeak_c:.3f}")

        if cpeak_c < 0.25:
            print("[RX] NO SIGNAL - check connections, frequency, gain")
            return

        # Find and decode frame (simplified)
        thr = max(0.25, 0.7 * cpeak_c)
        starts = []; i = 0
        while i < len(corr_c):
            if corr_c[i] < thr: i += 1; continue
            j, pk = i, i; lim = min(len(corr_c), i+L)
            while j < lim and corr_c[j] >= thr:
                if corr_c[j] > corr_c[pk]: pk = j
                j += 1
            fs = max(0, (pk - L + 1) - GUARD_LEN * SPS)
            if not starts or fs - starts[-1] > L: starts.append(fs)
            i = max(j, pk + L//2)

        for fs in starts[:1]:
            mf = matched_filter(buf, SPS, ALPHA, SPAN)
            approx = fs + GUARD_LEN * SPS + SPAN * SPS
            win = 2 * SPAN * SPS
            lo = max(0, approx - win); hi = min(len(mf) - PREAMBLE_LEN * SPS, approx + win)
            bo, bp, bc = approx, 0, -1.0
            for off in range(lo, hi):
                for ph in range(SPS):
                    cd = mf[off+ph::SPS][:PREAMBLE_LEN]
                    d = np.abs(np.dot(cd, ps.conj()))
                    if d > bc: bc, bo, bp = d, off, ph
            iq0 = bo + bp - GUARD_LEN * SPS
            while iq0 < 0: iq0 += SPS
            sf = mf[iq0::SPS]; syms = sf[GUARD_LEN:]
            if len(syms) > GUARD_LEN: syms = syms[:-GUARD_LEN]
            pos = PREAMBLE_LEN
            if pos + 32 > len(syms): continue
            rsync = bpsk_demod(syms[pos:pos+16]); pos += 16
            if not np.array_equal(rsync, sb):
                print(f"[RX] sync mismatch at frame {fs}")
                continue
            lb = bpsk_demod(syms[pos:pos+16]); pos += 16
            ba = np.asarray(lb, dtype=np.uint8)
            if len(ba) % 8: ba = np.pad(ba, (0, 8 - len(ba) % 8))
            rl = int.from_bytes(np.packbits(ba)[:2], "big")
            bn = (rl + 4) * 8
            if pos + bn > len(syms): continue
            rb = bpsk_demod(syms[pos:pos+bn])
            ba2 = np.asarray(rb, dtype=np.uint8)
            if len(ba2) % 8: ba2 = np.pad(ba2, (0, 8 - len(ba2) % 8))
            dc = np.packbits(ba2).tobytes()
            pl = dc[:-4]; rc = struct.unpack(">I", dc[-4:])[0]
            if (zlib.crc32(pl) & 0xFFFFFFFF) != rc:
                print(f"[RX] CRC fail"); continue
            print(f"\n[RX] *** SUCCESS! {len(pl)} bytes decoded ***")
            print(f"[RX] content: {pl.decode('utf-8','replace')}")
            Path("decoded_test.txt").write_bytes(pl)

if __name__ == "__main__":
    main()
