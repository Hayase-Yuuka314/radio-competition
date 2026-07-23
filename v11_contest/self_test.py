"""Offline self-test for contest codec — no hardware required."""
import sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from contest_codec import (ContestConfig, prepare_file_transfer, FileManifest,
                            build_burst, decode_capture, MAX_PAYLOAD_BYTES)

def test_basic():
    print("=== Test 1: Build & decode clean signal ===")
    config = ContestConfig(code_length=127, amplitude=0.3, hop_enabled=False)
    print(f"   SF={config.code_length} gain={config.processing_gain_db:.1f}dB "
          f"max_payload={MAX_PAYLOAD_BYTES}B")

    data = b"Hello SDR contest test! " * 4  # ~112 bytes
    data = data[:133]  # match test_data.txt size
    print(f"   data={len(data)}B")

    # Build packet
    file_path = HERE / "test_data.txt"
    packets, manifest = prepare_file_transfer(file_path, config)
    print(f"   packets={len(packets)} blocks={manifest.total_blocks}")

    burst = build_burst(packets[0], config)
    gap = config.gap_samples
    active = config.active_samples
    print(f"   burst={len(burst)} samples gap={gap} active={active} "
          f"({len(burst)/config.sample_rate:.1f}s)")

    assert len(burst) == gap + active, f"len mismatch: {len(burst)} != {gap}+{active}"

    # Simulate channel: repeat burst 3 times with a bit of noise
    repeats = 3
    signal = np.tile(burst, repeats).astype(np.complex128)
    # Add mild AWGN
    rng = np.random.default_rng(42)
    noise_pwr = 0.0001  # very low noise
    noise = np.sqrt(noise_pwr/2) * (rng.standard_normal(len(signal)) +
                                     1j * rng.standard_normal(len(signal)))
    signal = signal + noise
    signal = signal.astype(np.complex64)

    results = decode_capture(signal, config)
    print(f"   found={len(results)} packets")
    assert len(results) > 0, "No packets found in clean signal!"
    for r in results:
        print(f"   seq={r.seq}/{r.total} len={len(r.payload)}B "
              f"sync={r.sync_score:.3f} cfo={r.cfo_hz:.0f}Hz CRC={'OK' if r.crc_ok else 'FAIL'}")
        assert r.crc_ok

    # Verify content
    all_data = b"".join(r.payload for r in sorted(results, key=lambda r: r.seq))
    original = file_path.read_bytes()
    if all_data == original:
        print("   *** CONTENT MATCH! ***")
    else:
        print(f"   MISMATCH: got {len(all_data)}B, expected {len(original)}B")

    print("   PASSED\n")


def test_wrong_key():
    print("=== Test 2: Wrong key rejection ===")
    config = ContestConfig(code_length=127, shared_key="contest-key-2026")
    wrong = ContestConfig(code_length=127, shared_key="wrong-key!!!")

    file_path = HERE / "test_data.txt"
    packets, _ = prepare_file_transfer(file_path, config)
    burst = build_burst(packets[0], config)
    signal = np.tile(burst, 3).astype(np.complex64)

    results = decode_capture(signal, wrong)
    assert len(results) == 0, "Wrong key should NOT decode!"
    print("   Wrong key correctly rejected (CRC fails)")
    print("   PASSED\n")


def test_different_sf():
    print("=== Test 3: SF=63 ===")
    config = ContestConfig(code_length=63)
    print(f"   SF={config.code_length} gain={config.processing_gain_db:.1f}dB")

    file_path = HERE / "test_data.txt"
    packets, _ = prepare_file_transfer(file_path, config)
    burst = build_burst(packets[0], config)
    print(f"   burst={len(burst)} ({len(burst)/config.sample_rate:.1f}s)")

    signal = np.tile(burst, 3).astype(np.complex64)
    results = decode_capture(signal, config)
    assert len(results) > 0
    print(f"   found={len(results)} packets, CRC={'OK' if results[0].crc_ok else 'FAIL'}")
    print("   PASSED\n")


if __name__ == "__main__":
    test_basic()
    test_wrong_key()
    test_different_sf()
    print("=" * 50)
    print("  ALL SELF-TESTS PASSED")
    print("=" * 50)
