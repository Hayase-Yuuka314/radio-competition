"""评估 CLI。"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import numpy as np
from wireless_competition.evaluation.metrics import summarize_metrics
from wireless_competition.evaluation.monte_carlo import run_monte_carlo


def main():
    ap = argparse.ArgumentParser(description="Evaluate system performance")
    ap.add_argument("--n-seeds", type=int, default=20, help="Monte Carlo seeds")
    ap.add_argument("--snr-db", type=float, default=10.0)
    ap.add_argument("--data-size", type=int, default=1024)
    ap.add_argument("--modulation", type=str, default="bpsk", choices=["bpsk","qpsk"])
    ap.add_argument("--output", type=str, default="artifacts/reports/eval.json")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    from wireless_competition.common.types import ModulationType, FECType
    mod = ModulationType.BPSK if args.modulation == "bpsk" else ModulationType.QPSK

    def run_one(seed, **kw):
        from wireless_competition.tx.pipeline import TXPipeline
        from wireless_competition.channel.pipeline import ChannelPipeline
        from wireless_competition.rx.sim_receiver import SimulationReceiver
        from wireless_competition.common.types import ChannelConfig, RxProfile

        data = np.random.default_rng(seed).bytes(args.data_size)
        tx = TXPipeline(modulation=mod, fec_type=FECType.NONE, block_size=args.data_size, seed=seed)
        frames = tx.process_file(data)
        ch = ChannelPipeline(ChannelConfig(snr_db=args.snr_db))
        rx = SimulationReceiver(profile=RxProfile(modulation=mod), seed=seed)
        rng = np.random.default_rng(seed)

        correct = 0
        for f in frames:
            co = ch.apply(f, 2e6, rng)
            r = rx.process_frame(co.iq, guard_symbols=16)
            if r.payload_crc_pass:
                correct += len(r.payload_bytes)

        ber_val = 1.0 - correct / len(data) if len(data) > 0 else 0.0
        return {"ber": ber_val, "per": 0.0 if correct == len(data) else 1.0,
                "goodput_bps": correct * 8 / 1.0}

    print(f"Running {args.n_seeds}-seed Monte Carlo @ SNR={args.snr_db}dB...")
    summary = run_monte_carlo(run_one, n_seeds=args.n_seeds, base_seed=args.seed)

    # Save
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"Saved to {out}")

    # Print summary
    g = summary.get("goodput_bps", {})
    print(f"Goodput: mean={g.get('mean',0):.1f} p5={g.get('p5',0):.1f} bps")
    print(f"Failure rate: {summary.get('failure_rate', 0):.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
