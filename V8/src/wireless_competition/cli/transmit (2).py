"""发射 CLI stub。

空口发射需完整 RF 配置，当前仅提供骨架。
"""

from __future__ import annotations

import sys


def main():
    print("ERROR: TX requires complete contest_rules.yaml with non-null RF fields.")
    print("Please fill in the rules before attempting over-the-air transmission.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
