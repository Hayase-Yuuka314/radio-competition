"""集成测试：端到端 TX → Channel → RX。

覆盖理想/高斯信道下的完整文件回环。
"""

import numpy as np
import pytest

from wireless_competition.channel.pipeline import ChannelPipeline
from wireless_competition.common.types import (
    ChannelConfig,
    FECType,
    ModulationType,
    ProfileID,
    RxProfile,
)
from wireless_competition.file_protocol.assembler import FileAssembler
from wireless_competition.rx.sim_receiver import SimulationReceiver
from wireless_competition.tx.pipeline import TXPipeline


def _random_data(size: int, seed: int = 42) -> bytes:
    rng = np.random.default_rng(seed)
    return rng.bytes(size)


def _run_end_to_end(
    data: bytes,
    modulation: ModulationType = ModulationType.BPSK,
    fec_type: FECType = FECType.NONE,
    snr_db: float = 30.0,
    cfo_hz: float = 0.0,
    seed: int = 42,
    block_size: int = 256,
) -> dict:
    """运行一次端到端仿真并返回指标。"""
    rng = np.random.default_rng(seed)

    tx = TXPipeline(
        modulation=modulation,
        fec_type=fec_type,
        block_size=block_size,
        seed=seed,
    )
    frames = tx.process_file(data)

    ch_config = ChannelConfig(snr_db=snr_db, cfo_hz=cfo_hz)
    channel = ChannelPipeline(ch_config)

    rx = SimulationReceiver(
        profile=RxProfile(modulation=modulation, fec_type=fec_type),
        seed=seed,
    )

    correct_bytes = 0
    total_frames = len(frames)
    failed_frames = 0
    assembler = FileAssembler()

    for frame_iq in frames:
        ch_out = channel.apply(frame_iq, 2.0e6, rng)
        result = rx.process_frame(ch_out.iq, guard_symbols=16)

        if result.payload_crc_pass and result.metadata is not None:
            seq = result.metadata.block_sequence
            start = seq * block_size
            end = min(start + len(result.payload_bytes), len(data))
            expected = data[start:end]
            correct_bytes += sum(
                1 for a, b in zip(expected, result.payload_bytes[:len(expected)])
                if a == b
            )
            assembler.accept_raw(
                file_id=result.metadata.file_id,
                block_seq=seq,
                total_blocks=result.metadata.total_blocks,
                payload=result.payload_bytes,
            )
        else:
            failed_frames += 1

    return {
        "total_frames": total_frames,
        "failed_frames": failed_frames,
        "correct_bytes": correct_bytes,
        "total_bytes": len(data),
        "complete": assembler.is_complete(0),
    }


# ── 测试 ─────────────────────────────────────────────────────

class TestIdealBPSK:
    """理想信道（无噪声）BPSK 端到端。"""

    def test_small_file_no_noise(self):
        """小文件在无噪声下必须逐字节恢复。"""
        data = _random_data(200, seed=1)
        metrics = _run_end_to_end(
            data,
            modulation=ModulationType.BPSK,
            fec_type=FECType.NONE,
            snr_db=100.0,  # 无噪声
            block_size=200,
            seed=1,
        )
        assert metrics["correct_bytes"] == 200
        assert metrics["failed_frames"] == 0
        assert metrics["complete"]

    def test_256_bytes_no_noise(self):
        """恰好 256 字节。"""
        data = _random_data(256, seed=2)
        metrics = _run_end_to_end(
            data, ModulationType.BPSK, FECType.NONE,
            snr_db=100.0, block_size=256, seed=2,
        )
        assert metrics["correct_bytes"] == 256

    def test_random_binary_content(self):
        """全0、全1和随机内容都能正确处理。"""
        for content in [b"\x00" * 128, b"\xff" * 128, _random_data(128, 99)]:
            metrics = _run_end_to_end(
                content, ModulationType.BPSK, FECType.NONE,
                snr_db=100.0, block_size=128, seed=3,
            )
            assert metrics["correct_bytes"] == 128, f"Failed for content type"


class TestAWGNBPSK:
    """AWGN 下 BPSK 端到端。"""

    def test_high_snr_clean(self):
        """高 SNR 下应完全恢复。"""
        data = _random_data(256, seed=10)
        metrics = _run_end_to_end(
            data, ModulationType.BPSK, FECType.NONE,
            snr_db=20.0, block_size=256, seed=10,
        )
        assert metrics["correct_bytes"] == 256

    def test_medium_snr(self):
        """中 SNR 下应有较高恢复率。"""
        data = _random_data(256, seed=11)
        metrics = _run_end_to_end(
            data, ModulationType.BPSK, FECType.NONE,
            snr_db=10.0, block_size=256, seed=11,
        )
        # 中 SNR 下不应完全失败
        assert metrics["correct_bytes"] > 0

    def test_ber_decreases_with_snr(self):
        """BER 随 SNR 提高应单调下降。"""
        data = _random_data(512, seed=12)
        results = {}
        for snr in [3, 10, 20]:
            m = _run_end_to_end(
                data, ModulationType.BPSK, FECType.NONE,
                snr_db=snr, block_size=512, seed=12,
            )
            results[snr] = 1 - m["correct_bytes"] / m["total_bytes"]

        # 严格单调下降
        assert results[20] <= results[10] <= results[3]


class TestBPSKWithCFO:
    """含 CFO 的 BPSK 端到端。"""

    def test_small_cfo(self):
        """小 CFO 应能恢复。"""
        data = _random_data(256, seed=20)
        metrics = _run_end_to_end(
            data, ModulationType.BPSK, FECType.NONE,
            snr_db=30.0, cfo_hz=100.0, block_size=256, seed=20,
        )
        assert metrics["correct_bytes"] == 256


class TestFEC:
    """FEC 编码端到端。"""

    def test_convolutional_clean(self):
        """卷积码在无噪声下应完全恢复。"""
        data = _random_data(128, seed=30)
        metrics = _run_end_to_end(
            data, ModulationType.BPSK, FECType.CONVOLUTIONAL,
            snr_db=100.0, block_size=128, seed=30,
        )
        assert metrics["correct_bytes"] == 128

    def test_convolutional_awgn(self):
        """卷积码在高 SNR 下应工作。"""
        data = _random_data(128, seed=31)
        metrics = _run_end_to_end(
            data, ModulationType.BPSK, FECType.CONVOLUTIONAL,
            snr_db=15.0, block_size=128, seed=31,
        )
        assert metrics["correct_bytes"] > 0
