"""配置加载、合并与校验。

配置优先级：代码默认安全值 < 版本控制 YAML < 本地硬件配置 < 命令行显式覆盖。
每次运行将解析后的最终配置保存到实验输出目录。
"""

from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional

import yaml


# 默认安全配置：所有 RF 关键字段为 null
DEFAULT_CONFIG: dict[str, Any] = {
    "rules": {
        "confirmed": False,
        "contest_duration_s": None,
        "scoring_mode": None,
        "feedback_allowed": None,
        "half_duplex_allowed": None,
        "dynamic_frequency_allowed": None,
        "dynamic_modulation_allowed": None,
        "pretrained_models_allowed": None,
        "offline_iq_reprocessing_allowed": None,
    },
    "rf": {
        "allowed_bands_hz": None,
        "allowed_center_frequencies_hz": None,
        "max_occupied_bandwidth_hz": None,
        "max_tx_power_dbm": None,
        "max_tx_gain_db": None,
        "duty_cycle_limit": None,
    },
    "hardware": {
        "device_model": "NanoSDR_Pluto_compatible",
        "tx_uri": None,
        "rx_uri": None,
        "supported_sample_rates_hz": None,
        "supported_rf_bandwidths_hz": None,
    },
    "scoring": {
        "byte_exact": None,
        "block_crc_required": None,
        "partial_file_counts": None,
        "duplicate_data_counts_once": True,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """深度合并 override 到 base，返回新 dict。"""
    result = deepcopy(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_config(
    *paths: str | Path,
    base: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """加载并合并 YAML 配置。

    Args:
        *paths: 按优先级递增顺序的 YAML 文件路径。
        base: 基础配置，默认使用 DEFAULT_CONFIG。

    Returns:
        合并后的完整配置字典。
    """
    config = deepcopy(base if base is not None else DEFAULT_CONFIG)
    for p in paths:
        path = Path(p)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                override = yaml.safe_load(f) or {}
            config = _deep_merge(config, override)
    return config


def config_hash(config: dict[str, Any]) -> str:
    """计算配置字典的 SHA-256 哈希。"""
    canonical = json.dumps(config, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def save_resolved_config(config: dict[str, Any], output_dir: str | Path) -> Path:
    """将最终配置保存到实验输出目录。

    Args:
        config: 解析后的最终配置。
        output_dir: 输出目录。

    Returns:
        保存的文件路径。
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "resolved_config.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, default_flow_style=False, allow_unicode=True)
    return path


def validate_rf_for_tx(config: dict[str, Any]) -> list[str]:
    """检查 RF 字段是否足以执行空口发射。

    任何关键字段为 null 时返回缺失项列表。
    空列表表示可以安全发射。
    """
    missing: list[str] = []
    rf = config.get("rf", {})
    hw = config.get("hardware", {})

    checks = [
        ("rf.allowed_center_frequencies_hz", rf.get("allowed_center_frequencies_hz")),
        ("rf.max_occupied_bandwidth_hz", rf.get("max_occupied_bandwidth_hz")),
        ("rf.max_tx_gain_db", rf.get("max_tx_gain_db")),
        ("hardware.tx_uri", hw.get("tx_uri")),
    ]
    for name, val in checks:
        if val is None:
            missing.append(name)
    return missing


def load_contest_rules(config_dir: str | Path = "configs") -> dict[str, Any]:
    """便捷：加载比赛规则模板 + 本地硬件配置。"""
    config_dir = Path(config_dir)
    return load_config(
        config_dir / "contest_rules.yaml",
        config_dir / "hardware_local.yaml",
    )


def get_simulation_config(config_dir: str | Path = "configs") -> dict[str, Any]:
    """便捷：加载仿真配置。"""
    config_dir = Path(config_dir)
    return load_config(
        config_dir / "contest_rules.yaml",
        config_dir / "simulation_smoke.yaml",
    )
