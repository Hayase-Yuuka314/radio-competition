"""Quick simulation report."""
import os, time, numpy as np, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wireless_competition.fountain.raptorq import FountainEncoder, FountainDecoder
from wireless_competition.contest.dsss_pipeline import create_contest_dsss
from wireless_competition.channel.pipeline import ChannelPipeline
from wireless_competition.common.types import ChannelConfig
from wireless_competition.common.seeds import create_rng
from wireless_competition.adversarial.gold_code import (
    generate_team_code, verify_cross_correlation, gold_cross_correlation_bound,
)


def single_test(snr, size=3072):
    data = os.urandom(size)
    enc, dec = create_contest_dsss(team_id=0, spreading_factor=128)
    fenc = FountainEncoder(data, block_size=128, file_id=0)
    fdec = FountainDecoder()
    K = fenc.source_blocks
    rng = create_rng(42)
    ch = ChannelPipeline(ChannelConfig(snr_db=snr, enable_awgn=True))
    pkt_iter = fenc.encode_systematic_stream()
    buf = np.array([], dtype=np.complex64)
    for _ in range(K + 50):
        pkt = next(pkt_iter)
        iq = ch.apply(enc.encode_packet(pkt), 2e6, rng).iq
        buf = np.concatenate([buf, iq])
        if len(buf) > 200000:
            for fp in dec.process_stream(buf.real.astype(np.float64)[:150000]):
                fdec.add_packet(fp)
            buf = buf[100000:]
        if fdec.can_decode():
            d = fdec.decode()
            return d is not None and d[:len(data)] == data
    return False


def multi_test(n, snr):
    data, encs, decs, fdecs, iters, uniq = {}, {}, {}, {}, {}, {}
    for tid in range(n):
        data[tid] = os.urandom(2048)
        encs[tid], decs[tid] = create_contest_dsss(team_id=tid, spreading_factor=128)
        fdecs[tid] = FountainDecoder()
        iters[tid] = FountainEncoder(data[tid], 128, file_id=tid).encode_systematic_stream()
        uniq[tid] = set()
    rng = create_rng(42)
    ch = ChannelPipeline(ChannelConfig(snr_db=snr, enable_awgn=True))
    ok = set()
    for _ in range(60):
        sigs = []
        for tid in range(n):
            if tid in ok:
                sigs.append(np.array([], dtype=np.complex64))
                continue
            iqs = []
            for __ in range(3):
                try:
                    iqs.append(encs[tid].encode_packet(next(iters[tid])))
                except StopIteration:
                    break
            sigs.append(np.concatenate(iqs) if iqs else np.array([], dtype=np.complex64))
        ml = max(len(s) for s in sigs)
        if ml == 0:
            break
        summed = np.zeros(ml, dtype=np.complex64)
        for s in sigs:
            if len(s):
                summed[:len(s)] += s
        noisy = ch.apply(summed, 2e6, rng).iq.real.astype(np.float64)
        for tid in range(n):
            if tid in ok:
                continue
            for fp in decs[tid].process_stream(noisy):
                uniq[tid].add(fp.packet_id)
                fdecs[tid].add_packet(fp)
            fd = fdecs[tid]
            if fd.is_k_known and fd.can_decode():
                d = fd.decode()
                if d is not None and d[:len(data[tid])] == data[tid]:
                    ok.add(tid)
        if len(ok) == n:
            break
    return len(ok)


if __name__ == "__main__":
    print("=" * 55)
    print("  SINGLE-TEAM  (3072B, SF=128, K=24)")
    print("=" * 55)
    for snr in [30, 20, 15, 10, 5]:
        t0 = time.perf_counter()
        r = single_test(snr)
        t = time.perf_counter() - t0
        print(f"  SNR={snr:2d}dB  {'PASS' if r else 'FAIL'}  ({t:.1f}s)")

    print()
    print("=" * 55)
    print("  MULTI-TEAM CDMA  (2048B/team, same band, SF=128)")
    print("=" * 55)
    for n in [2, 4, 8, 12, 16]:
        for snr in [20, 15]:
            t0 = time.perf_counter()
            s = multi_test(n, snr)
            t = time.perf_counter() - t0
            bar = "#" * s + "." * (n - s)
            print(f"  N={n:2d} SNR={snr:2d}dB  [{bar}]  {s}/{n}  ({t:.1f}s)")

    print()
    print("=" * 55)
    print("  GOLD CODE X-CORR  (n=10, 8 teams)")
    print("=" * 55)
    codes = {t: generate_team_code(1023, t) for t in range(8)}
    cc = verify_cross_correlation(codes)
    print(f"  max_cc={cc['max_cc']:.4f}  mean_cc={cc['mean_cc']:.4f}  "
          f"bound={gold_cross_correlation_bound(10):.4f}")
