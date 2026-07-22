"""训练分类器 CLI。"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import numpy as np
from wireless_competition.ml.dataset import InterferenceDataset, generate_dataset, FeatureExtractor
from wireless_competition.ml.random_forest import InterferenceClassifier


def main():
    ap = argparse.ArgumentParser(description="Train interference classifier")
    ap.add_argument("--dataset", type=str, default="",
                    help="Path to .npz dataset (generates new if empty)")
    ap.add_argument("--n-estimators", type=int, default=80)
    ap.add_argument("--max-depth", type=int, default=12)
    ap.add_argument("--output", type=str, default="artifacts/models/ic_model.joblib")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    # Load or generate dataset
    if args.dataset and Path(args.dataset).exists():
        print(f"Loading dataset from {args.dataset}...")
        data = np.load(args.dataset, allow_pickle=True)
        ext = FeatureExtractor()
        # Trigger feature name init
        ext.extract(np.zeros(512, dtype=np.complex128))
        ds = InterferenceDataset(feature_extractor=ext)
        for i in range(len(data["X"])):
            ds._features.append(data["X"][i])
            ds._labels.append(str(data["y"][i]))
            ds._capture_ids.append(str(data["capture_ids"][i]))
        print(f"Loaded {ds.n_samples} samples")
    else:
        print("Generating training dataset...")
        ds = generate_dataset(
            n_captures_per_class=10, n_windows_per_capture=10,
            window_samples=512, snr_db_range=[0, 5, 10, 20], seed=args.seed,
            progress=True,
        )

    # Split
    train, val, test = ds.split_by_capture(seed=args.seed)
    print(f"Train: {train.n_samples}, Val: {val.n_samples}, Test: {test.n_samples}")

    # Train
    print(f"Training RF (n={args.n_estimators}, depth={args.max_depth})...")
    clf = InterferenceClassifier(
        n_estimators=args.n_estimators, max_depth=args.max_depth, random_state=args.seed)
    clf.fit(train)

    # Evaluate
    ev = clf.evaluate(test)
    print(f"Accuracy: {ev['accuracy']:.3f}")
    print(f"Macro F1: {ev['macro_f1']:.3f}")
    for cls, m in sorted(ev['per_class'].items()):
        print(f"  {cls}: f1={m['f1']:.2f}")

    # Save
    path = clf.save(args.output)
    print(f"Model saved to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
