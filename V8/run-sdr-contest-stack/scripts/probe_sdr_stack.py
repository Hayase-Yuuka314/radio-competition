#!/usr/bin/env python3
"""Inventory local SDR software and optionally run read-only hardware discovery."""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


COMMANDS: dict[str, list[str] | None] = {
    "conda": ["--version"],
    "mamba": ["--version"],
    "micromamba": ["--version"],
    "gnuradio-companion": ["--version"],
    "gnuradio-config-info": ["--version"],
    "grcc": ["--version"],
    "iio_info": ["--version"],
    "iio_attr": ["--version"],
    "iio_readdev": ["--version"],
    "iio_writedev": ["--version"],
    "SoapySDRUtil": ["--info"],
    "sdrangel": None,
    "sdrangelsrv": None,
    "inspectrum": None,
    "gqrx": None,
    "urh": ["--version"],
    "pyfda": ["--version"],
    "tshark": ["--version"],
    "wireshark": ["--version"],
    "uhd_find_devices": ["--version"],
    "hackrf_info": ["-v"],
    "bladeRF-cli": ["--version"],
    "rtl_sdr": None,
    "matlab": None,
    "octave": ["--version"],
    "cmake": ["--version"],
    "gcc": ["--version"],
    "clang": ["--version"],
}


PYTHON_MODULES: dict[str, list[str]] = {
    "gnuradio": ["gnuradio"],
    "pyadi-iio": ["adi", "pyadi-iio"],
    "pylibiio": ["iio", "pylibiio"],
    "SoapySDR": ["SoapySDR", "soapysdr"],
    "numpy": ["numpy"],
    "scipy": ["scipy"],
    "matplotlib": ["matplotlib"],
    "pandas": ["pandas"],
    "digital_rf": ["digital_rf", "digital-rf"],
    "sigmf": ["sigmf"],
    "h5py": ["h5py"],
    "pyzmq": ["zmq", "pyzmq"],
    "pytest": ["pytest"],
    "hypothesis": ["hypothesis"],
    "reedsolo": ["reedsolo"],
    "torch": ["torch"],
    "tensorflow": ["tensorflow"],
    "sionna": ["sionna"],
}


HARDWARE_PROBES: dict[str, list[str]] = {
    "libiio": ["iio_info", "-s"],
    "soapysdr": ["SoapySDRUtil", "--find"],
    "uhd": ["uhd_find_devices"],
    "hackrf": ["hackrf_info"],
}


def run_bounded(argv: list[str], timeout: float) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
        )
        combined = "\n".join(
            part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
        )
        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "output": combined[:16000],
            "truncated": len(combined) > 16000,
        }
    except subprocess.TimeoutExpired as exc:
        output = "\n".join(
            str(part).strip() for part in (exc.stdout, exc.stderr) if part
        )
        return {
            "ok": False,
            "timeout": True,
            "returncode": None,
            "output": output[:16000],
            "truncated": len(output) > 16000,
        }
    except OSError as exc:
        return {
            "ok": False,
            "returncode": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


def first_line(text: str) -> str | None:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return None


def command_inventory(include_versions: bool, timeout: float) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for command, version_args in COMMANDS.items():
        path = shutil.which(command)
        item: dict[str, Any] = {"found": path is not None, "path": path}
        if path and include_versions and version_args is not None:
            probe = run_bounded([path, *version_args], timeout)
            item["version_probe"] = {
                "ok": probe.get("ok", False),
                "returncode": probe.get("returncode"),
                "summary": first_line(probe.get("output", "")),
                "timeout": probe.get("timeout", False),
            }
        result[command] = item
    return result


def module_inventory() -> dict[str, Any]:
    packages_to_distributions = importlib.metadata.packages_distributions()
    result: dict[str, Any] = {}
    for label, candidates in PYTHON_MODULES.items():
        module_name = candidates[0]
        try:
            found = importlib.util.find_spec(module_name) is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            found = False

        distributions: list[str] = []
        for dist in packages_to_distributions.get(module_name, []):
            if dist not in distributions:
                distributions.append(dist)
        for candidate in candidates[1:]:
            if candidate not in distributions:
                try:
                    importlib.metadata.version(candidate)
                except importlib.metadata.PackageNotFoundError:
                    continue
                distributions.append(candidate)

        versions: dict[str, str] = {}
        for dist in distributions:
            try:
                versions[dist] = importlib.metadata.version(dist)
            except importlib.metadata.PackageNotFoundError:
                pass
        result[label] = {
            "module": module_name,
            "found": found,
            "distributions": versions,
        }
    return result


def conda_list(timeout: float) -> dict[str, Any]:
    conda = shutil.which("conda")
    if not conda:
        return {"ok": False, "error": "conda not found on PATH"}
    probe = run_bounded([conda, "list", "--json"], timeout)
    if not probe.get("ok"):
        return probe
    try:
        packages = json.loads(probe.get("output", "[]"))
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"invalid conda JSON: {exc}"}
    return {"ok": True, "packages": packages}


def hardware_inventory(timeout: float) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for label, argv in HARDWARE_PROBES.items():
        executable = shutil.which(argv[0])
        if executable is None:
            result[label] = {
                "available": False,
                "ran": False,
                "reason": f"{argv[0]} not found",
            }
            continue
        result[label] = {
            "available": True,
            "ran": True,
            "command": [executable, *argv[1:]],
            "result": run_bounded([executable, *argv[1:]], timeout),
        }
    return result


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    modules = module_inventory()
    commands = command_inventory(args.versions, args.timeout)
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": {
            "platform": platform.platform(),
            "system": platform.system(),
            "machine": platform.machine(),
            "python_executable": sys.executable,
            "python_version": platform.python_version(),
            "conda_prefix": os.environ.get("CONDA_PREFIX"),
            "conda_default_env": os.environ.get("CONDA_DEFAULT_ENV"),
        },
        "commands": commands,
        "python_modules": modules,
        "capability_summary": {
            "radio_environment": bool(
                commands["conda"]["found"] or commands["mamba"]["found"]
            ),
            "gnuradio": bool(
                modules["gnuradio"]["found"]
                or commands["gnuradio-companion"]["found"]
            ),
            "pluto_python": bool(
                modules["pyadi-iio"]["found"]
                and modules["pylibiio"]["found"]
                and modules["numpy"]["found"]
            ),
            "pluto_libiio_cli": bool(commands["iio_info"]["found"]),
            "cross_vendor_soapy": bool(
                modules["SoapySDR"]["found"] or commands["SoapySDRUtil"]["found"]
            ),
            "offline_dsp": bool(
                modules["numpy"]["found"] and modules["scipy"]["found"]
            ),
            "structured_iq": bool(
                modules["sigmf"]["found"] or modules["digital_rf"]["found"]
            ),
        },
    }
    if args.conda_list:
        report["conda_list"] = conda_list(args.timeout)
    if args.hardware:
        report["hardware_discovery"] = hardware_inventory(args.timeout)
    return report


def write_json(report: dict[str, Any], destination: str) -> None:
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if destination == "-":
        print(rendered)
        return
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hardware",
        action="store_true",
        help="run read-only libiio/Soapy/UHD/HackRF discovery",
    )
    parser.add_argument(
        "--versions",
        action="store_true",
        help="run bounded version probes for safe CLI tools",
    )
    parser.add_argument(
        "--conda-list",
        action="store_true",
        help="include the current environment's conda package list",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=8.0,
        help="per-command timeout in seconds (default: 8)",
    )
    parser.add_argument(
        "--json",
        default="-",
        metavar="PATH",
        help="write JSON to PATH or '-' for stdout (default: '-')",
    )
    args = parser.parse_args()
    if not (0.1 <= args.timeout <= 60.0):
        parser.error("--timeout must be between 0.1 and 60 seconds")
    return args


def main() -> int:
    args = parse_args()
    write_json(build_report(args), args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

