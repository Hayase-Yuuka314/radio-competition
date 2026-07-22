"""DSSS 帧级集成测试。"""

import numpy as np
import pytest

from wireless_competition.adversarial.dsss import SpreadingCodeManager
from wireless_competition.adversarial.frame import (
    dsss_build_frame,
    dsss_receive_frame,
    dsss_frame_end_to_end,
)
from wireless_competition.common.types import FrameMetadata


class TestDSSSFrame:
    def test_build_and_receive_clean(self):
        """干净信道：一帧往返完全恢复。"""
        code_mgr = SpreadingCodeManager(our_team_id=0, code_length=255)  # 255确保足够增益
        code = code_mgr.our_code

        meta = FrameMetadata(
            file_id=0, block_sequence=0, total_blocks=1, payload_length=50,
        )
        payload = b"hello dsss frame test!" * 3  # ~63 bytes

        chips = dsss_build_frame(payload, meta, code)
        result = dsss_receive_frame(chips, code)

        assert result["frame_detected"]
        assert result["payload_crc_pass"]
        assert result["payload_bytes"] == payload
        assert result["metadata"].file_id == 0
        assert result["metadata"].block_sequence == 0

    def test_noisy_channel(self):
        """AWGN 下正确恢复（SNR 适中）。"""
        code_mgr = SpreadingCodeManager(our_team_id=0, code_length=255)
        code = code_mgr.our_code
        rng = np.random.default_rng(42)

        meta = FrameMetadata(
            file_id=1, block_sequence=3, total_blocks=10, payload_length=100,
        )
        payload = np.random.default_rng(1).bytes(100)

        chips = dsss_build_frame(payload, meta, code)

        # 加噪声：SNR=5dB
        power = np.mean(chips ** 2)
        noise_power = power / (10 ** (5 / 10))
        noise = np.sqrt(noise_power) * rng.standard_normal(len(chips))
        noisy = chips + noise

        result = dsss_receive_frame(noisy, code)
        assert result["frame_detected"]
        assert result["payload_crc_pass"]
        assert result["payload_bytes"] == payload

    def test_wrong_code_fails(self):
        """错误码解扩应该失败（加噪声防止纯净信号穿透）。"""
        code_mgr = SpreadingCodeManager(our_team_id=0, code_length=1023)
        wrong_code = SpreadingCodeManager(our_team_id=1, code_length=1023).our_code
        rng = np.random.default_rng(42)

        meta = FrameMetadata(file_id=0, block_sequence=0, total_blocks=1, payload_length=30)
        payload = b"x" * 30

        chips = dsss_build_frame(payload, meta, code_mgr.our_code)

        # 加少量噪声使纯净信号无法通过错误码解扩
        power = np.mean(chips ** 2)
        noise = np.sqrt(power / (10 ** (10 / 10))) * rng.standard_normal(len(chips))
        noisy = chips + noise

        result = dsss_receive_frame(noisy, wrong_code)
        assert not result["payload_crc_pass"], f"Wrong code should fail, got {result['failure_reason']}"


class TestDSSSFrameEndToEnd:
    def test_single_block(self):
        """单块文件端到端。"""
        data = np.random.default_rng(42).bytes(200)
        r = dsss_frame_end_to_end(data, code_length=255, snr_db=10, block_size=200, seed=42)
        assert r["correct_bytes"] == 200
        assert r["complete"]

    def test_multi_block(self):
        """多块文件端到端（验证分块+重组）。"""
        data = np.random.default_rng(99).bytes(800)
        r = dsss_frame_end_to_end(data, code_length=127, snr_db=15, block_size=200, seed=42)
        assert r["complete"]
        assert r["correct_bytes"] == 800
        assert r["total_frames"] == 4

    def test_low_snr_still_works(self):
        """低 SNR 下 DSSS 处理增益生效。"""
        data = np.random.default_rng(1).bytes(256)
        r = dsss_frame_end_to_end(data, code_length=255, snr_db=-5, block_size=256, seed=42)
        # 码长255 PG=24dB, -5dB等效19dB → 应接近完美
        assert r["correct_bytes"] == 256
        assert r["complete"]

    def test_different_teams_independent(self):
        """不同队伍码互不干扰。"""
        data = np.random.default_rng(7).bytes(100)
        # 队伍0
        r0 = dsss_frame_end_to_end(data, team_id=0, code_length=255, snr_db=10, block_size=100, seed=42)
        assert r0["complete"]

        # 用队伍1的码去收队伍0的信号（加噪声）→ 应失败
        from wireless_competition.adversarial.frame import dsss_build_frame, dsss_receive_frame
        from wireless_competition.adversarial.dsss import SpreadingCodeManager
        from wireless_competition.common.types import FrameMetadata

        code0 = SpreadingCodeManager(our_team_id=0, code_length=1023).our_code
        code1 = SpreadingCodeManager(our_team_id=1, code_length=1023).our_code
        rng = np.random.default_rng(7)

        meta = FrameMetadata(file_id=0, block_sequence=0, total_blocks=1, payload_length=100)
        chips = dsss_build_frame(data, meta, code0)
        # 加噪声
        power = np.mean(chips ** 2)
        noise = np.sqrt(power / (10 ** (10 / 10))) * rng.standard_normal(len(chips))
        result = dsss_receive_frame(chips + noise, code1)
        assert not result["payload_crc_pass"], f"Different team code should fail, got {result['failure_reason']}"
