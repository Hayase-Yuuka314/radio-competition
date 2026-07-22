"""Transmit CLI - contest file transmission.

Sends a file using fountain codes + DSSS + TDD over PlutoSDR.

Usage:
    wireless-transmit <input_file> [--team-id 0] [--sim]
    wireless-transmit <input_file> --team-id 1 --tx-uri ip:192.168.2.1
"""

from __future__ import annotations

import argparse
import sys

from ..contest.orchestrator import (
    ContestConfig,
    ContestOrchestrator,
    OrchestratorState,
    create_team_orchestrator,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Contest file transmitter (Fountain + DSSS + TDD)",
    )
    parser.add_argument("input_file", help="File to transmit")
    parser.add_argument("--team-id", type=int, default=0,
                        help="Team identifier (0-N, determines Gold code)")
    parser.add_argument("--tx-uri", default="ip:192.168.2.1",
                        help="PlutoSDR TX device URI")
    parser.add_argument("--freq", type=float, default=2450e6,
                        help="Center frequency in Hz (default 2.45 GHz)")
    parser.add_argument("--sample-rate", type=float, default=2.0e6,
                        help="Sample rate in Hz")
    parser.add_argument("--spreading-factor", type=int, default=128,
                        help="DSSS spreading factor")
    parser.add_argument("--block-size", type=int, default=256,
                        help="Fountain code block size in bytes")
    parser.add_argument("--tx-gain", type=float, default=-10.0,
                        help="TX gain in dB")
    parser.add_argument("--sim", action="store_true",
                        help="Run in simulation mode (no hardware)")
    parser.add_argument("--sim-snr", type=float, default=20.0,
                        help="SNR for simulation mode")
    parser.add_argument("--output", default="",
                        help="Output path for recovered file (simulation e2e)")

    args = parser.parse_args(argv or sys.argv[1:])

    config = ContestConfig(
        team_id=args.team_id,
        tx_uri=args.tx_uri,
        center_frequency_hz=args.freq,
        sample_rate_hz=args.sample_rate,
        spreading_factor=args.spreading_factor,
        block_size=args.block_size,
        tx_gain_db=args.tx_gain,
        sim_mode=args.sim,
    )

    issues = config.validate()
    if issues:
        for issue in issues:
            print(f"WARNING: {issue}")

    orchestrator = create_team_orchestrator(
        team_id=args.team_id,
        sim_mode=args.sim,
        tx_uri=args.tx_uri,
    )

    try:
        if args.sim and args.output:
            result = orchestrator.run_simulation_e2e(
                args.input_file,
                output_path=args.output,
                snr_db=args.sim_snr,
            )
        else:
            result = orchestrator.transmit_file(args.input_file)
    except KeyboardInterrupt:
        print("\nTransmission interrupted.")
        return 1
    finally:
        orchestrator.close()

    if result.state == OrchestratorState.ERROR:
        print(f"ERROR: {result.last_error}")
        return 1

    print(f"\nDone. Packets sent: {result.packets_sent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
