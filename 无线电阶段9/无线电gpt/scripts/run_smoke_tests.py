"""冒烟测试脚本。

快速验证核心链路是否可运行。
用法: python scripts/run_smoke_tests.py
"""

import sys
from pathlib import Path

# 确保 src 在 path 中
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def run_smoke_tests():
    """运行冒烟测试。"""
    import subprocess
    import os

    root = Path(__file__).parent.parent

    # 只运行标记为 smoke 或快速测试
    print("=" * 60)
    print("Running smoke tests...")
    print("=" * 60)

    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            str(root / "tests" / "unit"),
            str(root / "tests" / "integration" / "test_end_to_end.py"),
            "-v",
            "-k", "test_small_file_no_noise or test_256_bytes_no_noise or test_bytes_bits or test_bpsk or test_crc32",
            "--tb=short",
        ],
        cwd=str(root),
        capture_output=False,
    )

    print("=" * 60)
    if result.returncode == 0:
        print("SMOKE TESTS PASSED")
    else:
        print("SMOKE TESTS FAILED")
    print("=" * 60)

    return result.returncode


if __name__ == "__main__":
    sys.exit(run_smoke_tests())
