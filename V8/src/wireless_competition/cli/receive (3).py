"""接收 CLI stub。"""

import sys

def main():
    print("ERROR: RX requires complete contest_rules.yaml with non-null RF fields.")
    return 1

if __name__ == "__main__":
    sys.exit(main())
