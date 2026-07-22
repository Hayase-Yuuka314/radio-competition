"""回归测试：固定种子的确定性验证。

确保已知良好场景不会因代码变更而退化。
"""

import numpy as np
import pytest

from wireless_competition.channel.pipeline import ChannelPipeline
from wireless_competition.common.types import (
    ChannelConfig,
    FECType,
    ModulationType,
    RxProfile,
)
from wireless_competition.rx.pipeline import Receiver
from wireless_competition.tx.pipeline import TXPipeline


# 已知良好场景
KNOWN_SCENARIOS = [
    {
        "name": "bpsk_ideal_256B",
        "data_seed": 1,
        "block_size": 256,
        "modulation": ModulationType.BPSK,
        "fec": FECType.NONE,
        "snr_db": 100.0,
        "cfo_hz": 0.0,
        "expected_correct_bytes": 256,
    },
    {
        "name": "bpsk_awgn_30dB_256B",
        "data_seed": 2,
        "block_size": 256,
        "modulation": ModulationType.BPSK,
        "fec": FECType.NONE,
        "snr_db": 30.0,
        "cfo_hz": 0.0,
        "expected_correct_bytes": 256,
    },
]


@pytest.mark.regression
@pytest.mark.parametrize("scenario", KNOWN_SCENARIOS, ids=lambda s: s["name"])
def test_regression_scenarios(scenario):
    """回归：固定种子场景结果不变。"""
    rng = np.random.default_rng(42)
    data = rng.bytes(scenario["data_seed"] * 100 + scenario["block_size"])[:scenario["block_size"]]

    tx = TXPipeline(
        modulation=scenario["modulation"],
        fec_type=scenario["fec"],
        block_size=scenario["block_size"],
        seed=42,
    )
    frames = tx.process_file(data)

    ch_config = ChannelConfig(
        snr_db=scenario["snr_db"],
        cfo_hz=scenario["cfo_hz"],
    )
    channel = ChannelPipeline(ch_config)
    rx = Receiver(
        profile=RxProfile(
            modulation=scenario["modulation"],
            fec_type=scenario["fec"],
        ),
        seed=42,
    )

    correct_bytes = 0
    for frame_iq in frames:
        ch_out = channel.apply(frame_iq, 2.0e6, rng)
        results = rx.process(ch_out.iq, 2.0e6)
        for r in results:
            if r.payload_crc_pass and r.metadata is not None:
                seq = r.metadata.block_sequence
                start = seq * scenario["block_size"]
                end = min(start + len(r.payload_bytes), len(data))
                expected = data[start:end]
                correct_bytes += sum(
                    1 for a, b in zip(expected, r.payload_bytes[:len(expected)]) if a == b
                )

    assert correct_bytes >= scenario["expected_correct_bytes"], (
        f"{scenario['name']}: expected ≥{scenario['expected_correct_bytes']}, "
        f"got {correct_bytes}"
    )
