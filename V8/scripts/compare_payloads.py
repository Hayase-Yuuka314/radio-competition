#!/usr/bin/env python
# scripts/compare_payloads.py
# 比对原始文件与恢复文件，输出字节级差异报告。
"""用法:
  python scripts/compare_payloads.py reference.bin decoded.bin
  python scripts/compare_payloads.py reference.bin decoded.bin --json -
"""
import sys, hashlib, json, argparse


def compare(ref_path, dec_path, search_window=0):
    with open(ref_path, "rb") as f:
        ref = f.read()
    with open(dec_path, "rb") as f:
        dec = f.read()

    result = {
        "reference_size": len(ref),
        "decoded_size": len(dec),
        "sha256_match": hashlib.sha256(ref).hexdigest() == hashlib.sha256(dec).hexdigest(),
        "length_match": len(ref) == len(dec),
        "byte_errors": 0,
        "first_error_offset": None,
    }

    # 按最小长度比较
    min_len = min(len(ref), len(dec))
    errors = 0
    first = None
    for i in range(min_len):
        if ref[i] != dec[i]:
            errors += 1
            if first is None:
                first = i
    result["byte_errors"] = errors + abs(len(ref) - len(dec))
    result["first_error_offset"] = first

    # 逐比特比较（如果长度对齐）
    if len(ref) == len(dec):
        bit_errors = 0
        for i in range(len(ref)):
            diff = ref[i] ^ dec[i]
            bit_errors += bin(diff).count("1")
        result["bit_errors"] = bit_errors
        result["bit_error_rate"] = bit_errors / (len(ref) * 8)
    else:
        result["bit_errors"] = None

    result["byte_error_rate"] = result["byte_errors"] / max(len(ref), len(dec))
    result["exact_match"] = result["sha256_match"]

    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("reference", help="原始文件路径")
    ap.add_argument("decoded", help="恢复文件路径")
    ap.add_argument("--search-window", type=int, default=0)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    result = compare(args.reference, args.decoded, args.search_window)
    result["reference_path"] = args.reference
    result["decoded_path"] = args.decoded

    if args.json == "-":
        json.dump(result, sys.stdout, indent=2, default=str)
    else:
        print(f"Reference: {result['reference_size']} bytes")
        print(f"Decoded:   {result['decoded_size']} bytes")
        print(f"Length match: {result['length_match']}")
        print(f"SHA-256 match: {result['sha256_match']}")
        print(f"Byte errors: {result['byte_errors']}")
        if result['bit_errors'] is not None:
            print(f"Bit errors: {result['bit_errors']} (BER={result['bit_error_rate']:.6f})")
        print(f"Byte error rate: {result['byte_error_rate']:.6f}")
        if result['first_error_offset'] is not None:
            print(f"First error at byte: {result['first_error_offset']}")
        print(f"Exact match: {result['exact_match']}")
        return 0 if result['exact_match'] else 1


if __name__ == "__main__":
    sys.exit(main())
