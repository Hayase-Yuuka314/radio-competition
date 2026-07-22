"""单元测试：common 模块。

覆盖 types、config、seeds、logging、validation。
"""

import numpy as np
import pytest

from wireless_competition.common.types import (
    ChannelConfig,
    DecodeResult,
    FECType,
    FailureReason,
    FrameMetadata,
    ModulationType,
    ProfileID,
    RxProfile,
    SyncState,
)
from wireless_competition.common.config import (
    DEFAULT_CONFIG,
    config_hash,
    load_config,
    validate_rf_for_tx,
)
from wireless_competition.common.seeds import (
    create_rng,
    create_seed_sequence,
    set_all_seeds,
    set_base_seed,
)
from wireless_competition.common.validation import (
    check_finite,
    check_nyquist,
    check_positive,
    check_probability,
)


# ── Types ────────────────────────────────────────────────────

class TestFrameMetadata:
    def test_default_values(self):
        meta = FrameMetadata()
        assert meta.protocol_version == 1
        assert meta.file_id == 0
        assert meta.total_blocks == 1

    def test_custom_values(self):
        meta = FrameMetadata(
            file_id=42,
            block_sequence=3,
            total_blocks=10,
            payload_length=256,
            profile_id=ProfileID.P1_ROBUST,
        )
        assert meta.file_id == 42
        assert meta.block_sequence == 3
        assert meta.total_blocks == 10


class TestDecodeResult:
    def test_default_is_failure(self):
        r = DecodeResult()
        assert not r.frame_detected
        assert not r.payload_crc_pass

    def test_encode_decode(self):
        import json
        r = DecodeResult(
            frame_detected=True,
            payload_crc_pass=True,
            failure_reason=FailureReason.NONE,
        )
        # 可序列化
        d = json.dumps({"detected": r.frame_detected})
        assert "true" in d


# ── Config ───────────────────────────────────────────────────

class TestConfig:
    def test_default_has_null_rf(self):
        assert DEFAULT_CONFIG["rf"]["allowed_center_frequencies_hz"] is None

    def test_load_merge(self):
        import tempfile
        import os
        import yaml

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump({"rf": {"max_tx_gain_db": 10}}, f)
            path = f.name

        try:
            config = load_config(path)
            assert config["rf"]["max_tx_gain_db"] == 10
            # 未覆盖字段保持默认
            assert config["rf"]["allowed_center_frequencies_hz"] is None
        finally:
            os.unlink(path)

    def test_config_hash_reproducible(self):
        h1 = config_hash(DEFAULT_CONFIG)
        h2 = config_hash(DEFAULT_CONFIG)
        assert h1 == h2
        assert len(h1) == 16

    def test_validate_rf_for_tx_missing(self):
        missing = validate_rf_for_tx(DEFAULT_CONFIG)
        assert len(missing) > 0
        assert any("center_frequencies" in m for m in missing)


# ── Seeds ────────────────────────────────────────────────────

class TestSeeds:
    def test_base_seed(self):
        set_base_seed(42)
        assert create_rng().integers(0, 100) == create_rng().integers(0, 100)

    def test_create_seed_sequence(self):
        seeds = create_seed_sequence(10, base=42)
        assert len(seeds) == 10
        assert len(set(seeds)) == 10  # 全部不同

    def test_different_rngs(self):
        rng1 = create_rng(1)
        rng2 = create_rng(2)
        v1 = rng1.random()
        v2 = rng2.random()
        assert v1 != v2


# ── Validation ───────────────────────────────────────────────

class TestValidation:
    def test_check_finite_ok(self):
        check_finite(np.array([1.0, 2.0]))

    def test_check_finite_nan(self):
        with pytest.raises(ValueError, match="NaN"):
            check_finite(np.array([1.0, np.nan]))

    def test_check_finite_inf(self):
        with pytest.raises(ValueError, match="Inf"):
            check_finite(np.array([1.0, np.inf]))

    def test_check_positive(self):
        check_positive(1.0)
        with pytest.raises(ValueError):
            check_positive(0.0)
        with pytest.raises(ValueError):
            check_positive(-1.0)

    def test_check_probability(self):
        check_probability(0.5)
        with pytest.raises(ValueError):
            check_probability(1.5)

    def test_check_nyquist(self):
        check_nyquist(1000, 400)  # 没问题
        with pytest.raises(ValueError, match="Nyquist"):
            check_nyquist(1000, 600)
