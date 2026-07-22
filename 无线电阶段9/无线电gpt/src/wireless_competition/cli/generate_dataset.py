"""数据集生成 CLI。"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from wireless_competition.ml.dataset import generate_dataset


def main():
    ap = argparse.ArgumentParser(description="Generate interference dataset")
    ap.add_argument("--captures-per-class", type=int, default=10)
    ap.add_argument("--windows-per-capture", type=int, default=10)
    ap.add_argument("--window-samples", type=int, default=512)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--output", type=str, default="data/processed/dataset.npz")
    args = ap.parse_args()

    print(f"Generating dataset ({args.captures_per_class} captures x "
          f"{args.windows_per_capture} windows x 7 classes)...")
    ds = generate_dataset(
        n_captures_per_class=args.captures_per_class,
        n_windows_per_capture=args.windows_per_capture,
        window_samples=args.window_samples,
        snr_db_range=[0, 5, 10, 20],
        seed=args.seed,
        progress=True,
    )
    print(f"Done: {ds.n_samples} samples, {len(ds.unique_labels)} classes")

    # Save
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    import numpy as np
    np.savez(out, X=ds.X, y=ds.y, capture_ids=ds.capture_ids,
             feature_names=ds.extractor.feature_names)
    print(f"Saved to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
