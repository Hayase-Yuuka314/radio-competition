#!/usr/bin/env python
# scripts/validate_radio_plan.py
# RF 发射计划校验器 — 发射前强制通过。
"""用法:
  python scripts/validate_radio_plan.py --plan assets/radio-plan.example.json --constraints assets/contest-constraints.example.json
"""
import sys, json, argparse
from pathlib import Path


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate(plan, constraints):
    errors, warnings = [], []
    mode = plan.get("mode", "simulation")

    if mode == "simulation":
        return errors, warnings  # 仿真模式不校验 RF

    # 检查规则已确认
    if not constraints.get("rules_confirmed", False):
        errors.append("RULES_NOT_CONFIRMED: contest rules not confirmed")

    # 检查频率
    center = plan.get("center_frequency_hz")
    allowed = constraints.get("rf", {}).get("allowed_center_frequencies_hz", [])
    if center is None:
        errors.append("FREQ_NULL: center_frequency_hz is null")
    elif allowed and center not in allowed:
        errors.append(f"FREQ_UNAUTHORIZED: {center/1e6:.1f}MHz not in {[f/1e6 for f in allowed]}")

    # 检查带宽
    bw = plan.get("occupied_bandwidth_hz")
    max_bw = constraints.get("rf", {}).get("max_occupied_bandwidth_hz")
    if bw is None:
        errors.append("BW_NULL: occupied_bandwidth_hz is null")
    elif max_bw and bw > max_bw:
        errors.append(f"BW_EXCEEDS: {bw/1e3:.0f}kHz > max {max_bw/1e3:.0f}kHz")

    # 检查增益/功率
    gain = plan.get("tx_gain_db")
    max_gain = constraints.get("rf", {}).get("max_tx_gain_db")
    if gain is None and mode in ("cable", "ota"):
        errors.append("GAIN_NULL: tx_gain_db is null")
    elif max_gain is not None and gain is not None and gain > max_gain:
        errors.append(f"GAIN_EXCEEDS: {gain}dB > max {max_gain}dB")

    # 检查采样率合法性
    sr = plan.get("sample_rate_hz")
    if sr and sr <= 0:
        errors.append(f"SAMPLE_RATE_INVALID: {sr}")

    # 检查 URI
    uri = plan.get("device_uri")
    if not uri and mode != "simulation":
        errors.append("URI_NULL: no device URI")

    # 检查 duty cycle
    duty = plan.get("duty_cycle")
    max_duty = constraints.get("rf", {}).get("duty_cycle_limit")
    if duty and max_duty and duty > max_duty:
        errors.append(f"DUTY_CYCLE_EXCEEDS: {duty} > {max_duty}")

    # 同轴模式警告
    if mode == "cable":
        warnings.append("CABLE_MODE: ensure adequate attenuation between TX and RX")

    # 空口模式警告
    if mode == "ota":
        warnings.append("OTA_MODE: verify antenna, filter, and regulatory compliance")

    return errors, warnings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--constraints", required=True)
    args = ap.parse_args()

    plan = load_json(args.plan)
    constraints = load_json(args.constraints)
    errors, warnings = validate(plan, constraints)

    print(f"Plan: {plan.get('mode','?')} @ {plan.get('center_frequency_hz',0)/1e6:.1f}MHz")
    print(f"Constraints: rules_confirmed={constraints.get('rules_confirmed',False)}")
    print()

    for w in warnings:
        print(f"[WARN] {w}")
    for e in errors:
        print(f"[ERROR] {e}")

    if errors:
        print(f"\nVALIDATION FAILED: {len(errors)} error(s)")
        return 1
    else:
        print(f"\nVALIDATION PASSED ({len(warnings)} warning(s))")
        return 0


if __name__ == "__main__":
    sys.exit(main())
