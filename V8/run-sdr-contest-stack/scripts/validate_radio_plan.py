#!/usr/bin/env python3
"""Fail-closed validation for a finite SDR transmission plan."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any


def load_json(path: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def require_number(
    obj: dict[str, Any], key: str, location: str, errors: list[str]
) -> float | None:
    value = obj.get(key)
    if not finite_number(value):
        errors.append(f"{location}.{key} must be a finite number")
        return None
    return float(value)


def check_range(
    value: float | None,
    spec: Any,
    location: str,
    errors: list[str],
) -> None:
    if value is None or spec is None:
        return
    if not isinstance(spec, dict):
        errors.append(f"constraint {location} must be an object")
        return
    minimum = spec.get("min")
    maximum = spec.get("max")
    if minimum is not None:
        if not finite_number(minimum):
            errors.append(f"constraint {location}.min must be a finite number")
        elif value < float(minimum):
            errors.append(f"{location}={value:g} is below minimum {float(minimum):g}")
    if maximum is not None:
        if not finite_number(maximum):
            errors.append(f"constraint {location}.max must be a finite number")
        elif value > float(maximum):
            errors.append(f"{location}={value:g} exceeds maximum {float(maximum):g}")


def validate(plan: dict[str, Any], constraints: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if plan.get("schema_version") != 1:
        errors.append("plan.schema_version must equal 1")
    if constraints.get("schema_version") != 1:
        errors.append("constraints.schema_version must equal 1")

    mode = plan.get("mode")
    if mode not in {"simulation", "file", "cable", "ota"}:
        errors.append("plan.mode must be simulation, file, cable, or ota")

    device = plan.get("device")
    if not isinstance(device, dict):
        errors.append("plan.device must be an object")
    else:
        if not isinstance(device.get("driver"), str) or not device.get("driver", "").strip():
            errors.append("plan.device.driver must be a non-empty string")
        if mode in {"cable", "ota"} and (
            not isinstance(device.get("uri"), str) or not device.get("uri", "").strip()
        ):
            errors.append("plan.device.uri must explicitly bind the RF device")

    tx = plan.get("tx")
    if not isinstance(tx, dict):
        errors.append("plan.tx must be an object")
        tx = {}

    center = require_number(tx, "center_frequency_hz", "plan.tx", errors)
    sample_rate = require_number(tx, "sample_rate_sps", "plan.tx", errors)
    bandwidth = require_number(tx, "occupied_bandwidth_hz", "plan.tx", errors)
    duration = require_number(tx, "duration_s", "plan.tx", errors)

    for label, value in (
        ("center_frequency_hz", center),
        ("sample_rate_sps", sample_rate),
        ("occupied_bandwidth_hz", bandwidth),
        ("duration_s", duration),
    ):
        if value is not None and value <= 0:
            errors.append(f"plan.tx.{label} must be greater than zero")

    if sample_rate is not None and bandwidth is not None and bandwidth > sample_rate:
        errors.append("occupied bandwidth cannot exceed the complex sample rate")

    check_range(sample_rate, constraints.get("sample_rate_sps"), "sample_rate_sps", errors)
    check_range(
        bandwidth,
        constraints.get("occupied_bandwidth_hz"),
        "occupied_bandwidth_hz",
        errors,
    )
    check_range(duration, constraints.get("duration_s"), "duration_s", errors)

    cyclic = tx.get("cyclic")
    if not isinstance(cyclic, bool):
        errors.append("plan.tx.cyclic must be true or false")
    stop_method = tx.get("stop_method")
    if mode in {"cable", "ota"} or cyclic is True:
        if not isinstance(stop_method, str) or not stop_method.strip():
            errors.append("plan.tx.stop_method must define a deterministic stop action")

    level = tx.get("level")
    level_spec = constraints.get("tx_level")
    if not isinstance(level, dict):
        errors.append("plan.tx.level must be an object")
        level = {}
    level_value = require_number(level, "value", "plan.tx.level", errors)
    parameter = level.get("parameter")
    unit = level.get("unit")
    if not isinstance(parameter, str) or not parameter.strip():
        errors.append("plan.tx.level.parameter must be a non-empty string")
    if not isinstance(unit, str) or not unit.strip():
        errors.append("plan.tx.level.unit must be a non-empty string")

    if level_spec is not None:
        if not isinstance(level_spec, dict):
            errors.append("constraints.tx_level must be an object")
        else:
            expected_parameter = level_spec.get("parameter")
            expected_unit = level_spec.get("unit")
            if expected_parameter != parameter:
                errors.append(
                    "TX level parameter does not match the authorized constraint "
                    f"({parameter!r} != {expected_parameter!r})"
                )
            if expected_unit != unit:
                errors.append(
                    "TX level unit does not match the authorized constraint "
                    f"({unit!r} != {expected_unit!r})"
                )
            check_range(level_value, level_spec, "tx_level", errors)
    elif mode in {"cable", "ota"}:
        errors.append("constraints.tx_level is required for RF transmission")

    band_match: list[float] | None = None
    bands = constraints.get("allowed_tx_bands_hz")
    if bands is not None and not isinstance(bands, list):
        errors.append("constraints.allowed_tx_bands_hz must be an array")
        bands = []
    if isinstance(bands, list) and center is not None and bandwidth is not None:
        lower_edge = center - bandwidth / 2.0
        upper_edge = center + bandwidth / 2.0
        for index, band in enumerate(bands):
            if (
                not isinstance(band, list)
                or len(band) != 2
                or not finite_number(band[0])
                or not finite_number(band[1])
                or float(band[0]) >= float(band[1])
            ):
                errors.append(
                    f"constraints.allowed_tx_bands_hz[{index}] must be [low, high]"
                )
                continue
            low, high = float(band[0]), float(band[1])
            if lower_edge >= low and upper_edge <= high:
                band_match = [low, high]
        if mode == "ota" and band_match is None:
            errors.append(
                "the entire occupied spectrum is not contained in an authorized TX band"
            )

    if mode == "ota":
        if constraints.get("authorization_confirmed") is not True:
            errors.append("OTA transmission authorization is not confirmed")
        if constraints.get("physical_tx_setup_confirmed") is not True:
            errors.append("OTA antenna/filter/port setup is not confirmed")
        if not bands:
            errors.append("OTA transmission requires at least one exact authorized band")
    elif mode == "cable":
        if constraints.get("physical_tx_setup_confirmed") is not True:
            errors.append("cabled attenuation/dummy-load setup is not confirmed")
        if constraints.get("authorization_confirmed") is not True:
            warnings.append(
                "authorization_confirmed is false; keep the RF path fully contained"
            )
    else:
        warnings.append("non-RF mode: authorization and physical TX gates were not required")

    return {
        "valid": not errors,
        "mode": mode,
        "matched_authorized_band_hz": band_match,
        "errors": errors,
        "warnings": warnings,
    }


def render(result: dict[str, Any], json_destination: str | None) -> None:
    serialized = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if json_destination:
        if json_destination == "-":
            print(serialized)
        else:
            path = Path(json_destination)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(serialized + "\n", encoding="utf-8")
        return
    print("VALID" if result["valid"] else "INVALID")
    for warning in result["warnings"]:
        print(f"warning: {warning}")
    for error in result["errors"]:
        print(f"error: {error}", file=sys.stderr)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, help="radio plan JSON")
    parser.add_argument("--constraints", required=True, help="authorized constraints JSON")
    parser.add_argument(
        "--json",
        metavar="PATH",
        help="write structured result to PATH or '-' for stdout",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        plan = load_json(args.plan)
        constraints = load_json(args.constraints)
        result = validate(plan, constraints)
    except ValueError as exc:
        result = {"valid": False, "mode": None, "errors": [str(exc)], "warnings": []}
    render(result, args.json)
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

