#!/usr/bin/env python3
"""Compare a transmitted reference payload with decoded bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


BIT_COUNTS = tuple(bin(value).count("1") for value in range(256))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def alignment_metrics(reference: bytes, received: bytes, offset: int) -> dict[str, Any]:
    ref_start = max(0, -offset)
    rx_start = max(0, offset)
    overlap = min(len(reference) - ref_start, len(received) - rx_start)
    overlap = max(0, overlap)

    correct = 0
    bit_errors = 0
    if overlap:
        ref_view = memoryview(reference)[ref_start : ref_start + overlap]
        rx_view = memoryview(received)[rx_start : rx_start + overlap]
        for expected, actual in zip(ref_view, rx_view):
            if expected == actual:
                correct += 1
            bit_errors += BIT_COUNTS[expected ^ actual]

    missing_reference_bytes = len(reference) - overlap
    bit_errors_or_missing = bit_errors + 8 * missing_reference_bytes

    prefix = 0
    if ref_start == 0:
        while prefix < overlap:
            if reference[prefix] != received[rx_start + prefix]:
                break
            prefix += 1

    return {
        "offset": offset,
        "reference_start": ref_start,
        "received_start": rx_start,
        "overlap_bytes": overlap,
        "correct_bytes_in_overlap": correct,
        "incorrect_or_missing_reference_bytes": len(reference) - correct,
        "bit_errors_in_overlap": bit_errors,
        "bit_errors_or_missing": bit_errors_or_missing,
        "longest_correct_reference_prefix_bytes": prefix,
    }


def choose_alignment(
    reference: bytes,
    received: bytes,
    explicit_offset: int | None,
    search_window: int,
) -> dict[str, Any]:
    if explicit_offset is not None:
        candidates = [explicit_offset]
    else:
        candidates = range(-search_window, search_window + 1)
    metrics = [alignment_metrics(reference, received, offset) for offset in candidates]
    return max(
        metrics,
        key=lambda item: (
            item["correct_bytes_in_overlap"],
            -item["incorrect_or_missing_reference_bytes"],
            item["overlap_bytes"],
            -abs(item["offset"]),
            -item["offset"],
        ),
    )


def compare(
    reference_path: str,
    received_path: str,
    explicit_offset: int | None,
    search_window: int,
) -> dict[str, Any]:
    reference = Path(reference_path).read_bytes()
    received = Path(received_path).read_bytes()
    best = choose_alignment(reference, received, explicit_offset, search_window)

    ref_len = len(reference)
    correct = best["correct_bytes_in_overlap"]
    result = {
        "reference": {
            "path": str(Path(reference_path)),
            "bytes": ref_len,
            "sha256": sha256(reference),
        },
        "received": {
            "path": str(Path(received_path)),
            "bytes": len(received),
            "sha256": sha256(received),
        },
        "exact_file_match": reference == received,
        "alignment_search_window": search_window if explicit_offset is None else None,
        "best_alignment": best,
        "score": {
            "correct_reference_bytes": correct,
            "correct_fraction_of_reference": (correct / ref_len) if ref_len else 1.0,
            "byte_error_or_missing_rate": (
                best["incorrect_or_missing_reference_bytes"] / ref_len if ref_len else 0.0
            ),
            "bit_error_or_missing_rate": (
                best["bit_errors_or_missing"] / (8 * ref_len) if ref_len else 0.0
            ),
        },
        "notes": [
            "Correct bytes are positional after the selected alignment.",
            "Extra received bytes are reported by length but do not reduce the reference score.",
            "Use packet/sequence-aware scoring when the official judge deduplicates or reorders frames.",
        ],
    }
    return result


def write_result(result: dict[str, Any], destination: str | None) -> None:
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if destination:
        if destination == "-":
            print(rendered)
        else:
            path = Path(destination)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered + "\n", encoding="utf-8")
        return
    score = result["score"]
    best = result["best_alignment"]
    print(f"exact_file_match: {result['exact_file_match']}")
    print(f"best_received_offset: {best['offset']}")
    print(f"correct_reference_bytes: {score['correct_reference_bytes']}")
    print(f"correct_fraction_of_reference: {score['correct_fraction_of_reference']:.9f}")
    print(f"bit_error_or_missing_rate: {score['bit_error_or_missing_rate']:.9f}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", help="original transmitted payload")
    parser.add_argument("received", help="decoded payload")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--rx-offset",
        type=int,
        help="received index corresponding to reference byte 0",
    )
    group.add_argument(
        "--search-window",
        type=int,
        default=0,
        help="search offsets from -N through +N (default: 0)",
    )
    parser.add_argument("--json", metavar="PATH", help="write JSON to PATH or '-' for stdout")
    args = parser.parse_args()
    if args.search_window < 0 or args.search_window > 100000:
        parser.error("--search-window must be between 0 and 100000")
    return args


def main() -> int:
    args = parse_args()
    try:
        result = compare(args.reference, args.received, args.rx_offset, args.search_window)
    except OSError as exc:
        raise SystemExit(f"file error: {exc}") from exc
    write_result(result, args.json)
    return 0 if result["exact_file_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

