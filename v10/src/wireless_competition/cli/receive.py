"""Receive CLI - contest file reception.

Receives a file using fountain codes + DSSS + TDD over PlutoSDR.

Usage:
    wireless-receive [--team-id 0] [--output recovered.bin] [--sim]
    wireless-receive --team-id 1 --rx-uri ip:192.168.2.1 --output out.bin
"""

from __future__ import annotations

import argparse
import sys

from ..contest.orchestrator import (
    ContestConfig,
    ContestOrchestrator,
    create_team_orchestrator,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Contest file receiver (Fountain + DSSS + TDD)",
    )
    parser.add_argument("--team-id", type=int, default=0,
                        help="Team identifier (0-N, must match transmitter)")
    parser.add_argument("--rx-uri", default="ip:192.168.2.1",
                        help="PlutoSDR RX device URI")
    parser.add_argument("--freq", type=float, default=2450e6,
                        help="Center frequency in Hz (default 2.45 GHz)")
    parser.add_argument("--sample-rate", type=float, default=2.0e6,
                        help="Sample rate in Hz")
    parser.add_argument("--spreading-factor", type=int, default=128,
                        help="DSSS spreading factor")
    parser.add_argument("--rx-gain", type=float, default=40.0,
                        help="RX gain in dB")
    parser.add_argument("--output", default="",
                        help="Output file path for recovered data")
    parser.add_argument("--sim", action="store_true",
                        help="Run in simulation mode (no hardware)")

    args = parser.parse_args(argv or sys.argv[1:])

    label = f"team{args.team_id}"
    output = args.output or f"recovered_{label}.bin"

    orchestrator = create_team_orchestrator(
        team_id=args.team_id,
        sim_mode=args.sim,
        rx_uri=args.rx_uri,
    )

    try:
        result = orchestrator.receive_file(output)
    except KeyboardInterrupt:
        print("\nReception interrupted.")
        return 1
    finally:
        orchestrator.close()

    if result.file_complete:
        print(f"Successfully recovered {result.bytes_recovered} bytes → {output}")
        return 0
    else:
        print(f"Incomplete: {result.bytes_recovered} bytes "
              f"(packets: {result.packets_received})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
