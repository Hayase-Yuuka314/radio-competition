"""Multi-team contest simulation.

N teams transmit simultaneously in the same frequency band.
Each team uses a different Gold code (team_id → CDMA isolation).
All signals are summed with AWGN, then each team's receiver
attempts to decode only its own data.

Measures:
- Per-team packet recovery rate
- Fountain decode success/failure
- Effective throughput vs number of competing teams
"""

import os, sys, time, hashlib
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wireless_competition.fountain.raptorq import FountainEncoder, FountainDecoder
from wireless_competition.contest.dsss_pipeline import (
    ContestDSSSEncoder, ContestDSSSDecoder, DSSSConfig,
)
from wireless_competition.channel.pipeline import ChannelPipeline
from wireless_competition.common.types import ChannelConfig
from wireless_competition.common.seeds import create_rng


def run_contest(
    num_teams: int = 4,
    file_size: int = 2048,
    snr_db: float = 20.0,
    spreading_factor: int = 128,
    block_size: int = 128,
    max_packets_per_team: int = 200,
):
    """Run multi-team contest simulation.

    Args:
        num_teams: Number of competing teams (1-16).
        file_size: Bytes per team's test file.
        snr_db: AWGN SNR relative to one team's signal power.
        spreading_factor: DSSS code length.
        block_size: Fountain code block size.
        max_packets_per_team: Cap on packets sent per team.

    Returns:
        dict with per-team and aggregate results.
    """
    print(f"\n{'='*60}")
    print(f"Multi-Team Contest Simulation")
    print(f"  Teams: {num_teams} | SNR: {snr_db}dB | SF: {spreading_factor}")
    print(f"  File: {file_size}B per team | Block: {block_size}B")
    print(f"{'='*60}\n")

    rng = create_rng(42)
    channel = ChannelPipeline(ChannelConfig(snr_db=snr_db, enable_awgn=True))

    # Generate unique data per team
    team_data = {}
    team_encs = {}
    team_decs = {}
    team_fdecoders = {}
    team_pkt_iters = {}
    team_unique_pkts = {}
    team_k_values = {}

    for tid in range(num_teams):
        data = os.urandom(file_size)
        team_data[tid] = data

        dsss_cfg = DSSSConfig(team_id=tid, spreading_factor=spreading_factor)
        team_encs[tid] = ContestDSSSEncoder(dsss_cfg)
        team_decs[tid] = ContestDSSSDecoder(dsss_cfg)

        fenc = FountainEncoder(data, block_size=block_size, file_id=tid)
        team_pkt_iters[tid] = fenc.encode_systematic_stream()
        team_unique_pkts[tid] = set()
        team_k_values[tid] = fenc.source_blocks
        team_fdecoders[tid] = FountainDecoder()

    # Run simulation in rounds
    round_size = 4
    max_rounds = max_packets_per_team // round_size

    results = {}
    for tid in range(num_teams):
        results[tid] = {"sent": 0, "detected": 0, "unique": 0,
                        "decoded": False, "bytes_recovered": 0, "data_match": False}

    for rnd in range(max_rounds):
        round_signals = []

        for tid in range(num_teams):
            team_iqs = []
            for _ in range(round_size):
                try:
                    pkt = next(team_pkt_iters[tid])
                except StopIteration:
                    break
                iq = team_encs[tid].encode_packet(pkt)
                team_iqs.append(iq)
                results[tid]["sent"] += 1

            if team_iqs:
                combined = np.concatenate(team_iqs)
                round_signals.append(combined)

        if not round_signals:
            continue

        max_len = max(len(s) for s in round_signals)
        summed_signal = np.zeros(max_len, dtype=np.complex64)
        for s in round_signals:
            padded = np.zeros(max_len, dtype=np.complex64)
            padded[:len(s)] = s
            summed_signal += padded

        ch_out = channel.apply(summed_signal, sample_rate_hz=2e6, rng=rng)
        noisy_signal = ch_out.iq

        for tid in range(num_teams):
            sig_real = noisy_signal.real.astype(np.float64)
            window = 400000
            ovlp = 300000
            pos = 0
            while pos < len(sig_real):
                chunk = sig_real[pos:pos + window]
                pkts = team_decs[tid].process_stream(chunk)
                for fp in pkts:
                    if fp.packet_id not in team_unique_pkts[tid]:
                        team_unique_pkts[tid].add(fp.packet_id)
                    team_fdecoders[tid].add_packet(fp)
                pos += window - ovlp
                if len(chunk) < window:
                    break

            results[tid]["unique"] = len(team_unique_pkts[tid])
            results[tid]["detected"] = results[tid]["unique"]

            fd = team_fdecoders[tid]
            if fd.is_k_known and fd.can_decode() and not results[tid]["decoded"]:
                decoded = fd.decode()
                if decoded is not None:
                    results[tid]["decoded"] = True
                    results[tid]["bytes_recovered"] = len(decoded)
                    results[tid]["data_match"] = (
                        decoded[:len(team_data[tid])] == team_data[tid]
                    )

        all_done = all(results[t]["decoded"] for t in range(num_teams))
        if all_done:
            break

    print(f"\n{'='*60}")
    print(f"RESULTS")
    print(f"{'='*60}")
    header = f"{'Team':<6}{'K':<6}{'Sent':<8}{'Unique':<8}{'Recovered(B)':<14}{'Match':<8}"
    print(header)
    print("-" * 50)

    for tid in range(num_teams):
        r = results[tid]
        K = team_k_values[tid]
        m = "YES" if r["data_match"] else "NO"
        print(f"{tid:<6}{K:<6}{r['sent']:<8}{r['unique']:<8}{r['bytes_recovered']:<14}{m:<8}")

    ok = sum(1 for r in results.values() if r["data_match"])
    print(f"\n  Success: {ok}/{num_teams} teams")

    return results


if __name__ == "__main__":
    t0 = time.perf_counter()
    for n in [2, 4, 8]:
        run_contest(num_teams=n, file_size=2048, snr_db=20.0, spreading_factor=128,
                    max_packets_per_team=300)
    print(f"\nTotal: {time.perf_counter() - t0:.1f}s")
