"""核心数据类型定义。

所有模块共享的数据类型、枚举和 dataclass 定义。
单位命名规则：显式写在变量名中（_hz, _db, _s, _samples 等）。
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Any

import numpy as np


# ── 调制与编码 ──────────────────────────────────────────────

class ModulationType(str, Enum):
    """调制类型枚举。"""
    BPSK = "bpsk"
    QPSK = "qpsk"


class FECType(str, Enum):
    """前向纠错类型枚举。"""
    NONE = "none"
    REPETITION = "repetition"
    CONVOLUTIONAL = "convolutional"


class ProfileID(str, Enum):
    """物理层配置档位标识。"""
    P0_RESCUE = "p0_rescue"       # 极差环境保底 BPSK + 强FEC
    P1_ROBUST = "p1_robust"       # 常规稳健 BPSK/QPSK + 中强FEC
    P2_BALANCED = "p2_balanced"   # 默认档 QPSK + 中FEC
    P3_FAST = "p3_fast"           # 良好信道 QPSK + 弱FEC
    P4_NOTCH = "p4_notch"         # 窄带干扰 自适应陷波
    P5_BURST = "p5_burst"         # 突发干扰 深交织


# ── 同步状态 ──────────────────────────────────────────────────

class SyncState(str, Enum):
    """接收端同步状态机。"""
    IDLE = "idle"
    ENERGY_DETECTED = "energy_detected"
    PREAMBLE_FOUND = "preamble_found"
    CFO_CORRECTED = "cfo_corrected"
    TIMING_LOCKED = "timing_locked"
    HEADER_DECODED = "header_decoded"
    PAYLOAD_DECODING = "payload_decoding"
    CRC_PASS = "crc_pass"
    CRC_FAIL = "crc_fail"
    SEARCH = "search"
    RELOCK = "relock"


# ── 失败原因 ──────────────────────────────────────────────────

class FailureReason(str, Enum):
    """帧解码失败原因。"""
    NONE = "none"                       # 无失败
    NO_FRAME_DETECTED = "no_frame_detected"
    CFO_ESTIMATION_FAILED = "cfo_estimation_failed"
    TIMING_FAILED = "timing_failed"
    HEADER_CRC_FAIL = "header_crc_fail"
    PAYLOAD_CRC_FAIL = "payload_crc_fail"
    PAYLOAD_LENGTH_MISMATCH = "payload_length_mismatch"
    UNKNOWN = "unknown"


# ── 干扰标签体系 ──────────────────────────────────────────────

class InterferenceFamily(str, Enum):
    """干扰族类。"""
    CLEAN = "clean"
    TONE = "tone"
    MULTITONE = "multitone"
    SWEEP = "sweep"
    BROADBAND_NOISE = "broadband_noise"
    BANDLIMITED_NOISE = "bandlimited_noise"
    BURST = "burst"
    DIGITAL_SINGLE_CARRIER = "digital_single_carrier"
    OFDM_LIKE = "ofdm_like"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class SpectralRelation(str, Enum):
    """频谱关系。"""
    INBAND = "inband"
    BAND_EDGE = "band_edge"
    ADJACENT = "adjacent"
    OUT_OF_BAND = "out_of_band"


class TemporalPattern(str, Enum):
    """时间模式。"""
    CONTINUOUS = "continuous"
    BURSTY = "bursty"
    PERIODIC = "periodic"
    UNKNOWN = "unknown"


class Severity(str, Enum):
    """严重程度。"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"


# ── Dataclass 定义 ────────────────────────────────────────────

@dataclass
class FrameMetadata:
    """帧元数据（包头字段）。"""
    protocol_version: int = 1
    file_id: int = 0
    session_id: int = 0
    block_sequence: int = 0
    total_blocks: int = 1
    payload_length: int = 0              # 有效载荷字节数
    profile_id: ProfileID = ProfileID.P2_BALANCED
    repetition_id: int = 0               # 重复副本编号
    header_crc: int = 0


@dataclass
class DecodeResult:
    """接收端解码结果。"""
    frame_detected: bool = False
    header_crc_pass: bool = False
    payload_crc_pass: bool = False
    metadata: Optional[FrameMetadata] = None
    payload_bytes: bytes = b""
    raw_bit_errors: int = 0              # 仿真中可用
    post_fec_bit_errors: int = 0         # 仿真中可用
    snr_estimate_db: float = float("nan")
    evm_estimate: float = float("nan")
    cfo_estimate_hz: float = float("nan")
    profile_used: ProfileID = ProfileID.P1_ROBUST
    failure_reason: FailureReason = FailureReason.NONE
    sync_state: SyncState = SyncState.IDLE
    processing_time_s: float = 0.0
    # ML 相关
    model_prediction: Optional[str] = None
    model_confidence: float = 0.0
    is_ood: bool = False


@dataclass
class ChannelConfig:
    """信道/损伤配置。"""
    # AWGN
    snr_db: float = 30.0
    enable_awgn: bool = True
    # 干扰
    enable_interference: bool = False
    interference_type: InterferenceFamily = InterferenceFamily.CLEAN
    inr_db: float = -100.0
    # CFO
    cfo_hz: float = 0.0
    # 定时偏差 (fractional symbol)
    timing_offset_symbols: float = 0.0
    # 多径
    enable_multipath: bool = False
    channel_taps: list[complex] = field(default_factory=lambda: [1.0+0j])
    # 硬件损伤
    enable_dc_offset: bool = False
    dc_offset: complex = 0+0j
    enable_iq_imbalance: bool = False
    iq_gain_imbalance_db: float = 0.0
    iq_phase_imbalance_deg: float = 0.0
    enable_phase_noise: bool = False
    phase_noise_std_rad: float = 0.0
    enable_clipping: bool = False
    clipping_threshold: float = 1.0
    enable_quantization: bool = False
    quantization_bits: int = 16
    # 丢样
    enable_drop_samples: bool = False
    drop_probability: float = 0.0
    # 固定增益
    gain_db: float = 0.0


@dataclass
class ChannelOutput:
    """信道输出。"""
    iq: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.complex64))
    sample_rate_hz: float = 1.0
    ground_truth_snr_db: float = 30.0
    ground_truth_inr_db: float = -100.0
    ground_truth_cfo_hz: float = 0.0
    ground_truth_timing_offset: float = 0.0
    ground_truth_channel_taps: list[complex] = field(default_factory=list)
    events: dict[str, Any] = field(default_factory=dict)
    seed: int = 0
    config_hash: str = ""


@dataclass
class RxHardwareConfig:
    """接收硬件配置。"""
    uri: str = "ip:192.168.2.1"
    center_frequency_hz: float = 2.4e9
    sample_rate_hz: float = 2.0e6
    rf_bandwidth_hz: float = 2.0e6
    gain_mode: str = "manual"           # manual, slow_attack, fast_attack
    gain_db: float = 40.0
    buffer_size_samples: int = 32768


@dataclass
class TxHardwareConfig:
    """发射硬件配置。"""
    uri: str = "ip:192.168.2.1"
    center_frequency_hz: float = 2.4e9
    sample_rate_hz: float = 2.0e6
    rf_bandwidth_hz: float = 2.0e6
    attenuation_db: float = 10.0
    buffer_size_samples: int = 32768


@dataclass
class DeviceHealth:
    """设备健康状态。"""
    connected: bool = False
    uri: str = ""
    temperature_c: float = 0.0
    last_sample_time_s: float = 0.0
    dropped_samples: int = 0
    buffer_depth: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class RxProfile:
    """接收端配置档案。"""
    profile_id: ProfileID = ProfileID.P1_ROBUST
    modulation: ModulationType = ModulationType.BPSK
    fec_type: FECType = FECType.CONVOLUTIONAL
    fec_rate: float = 0.5
    samples_per_symbol: int = 8
    rrc_rolloff: float = 0.35
    rrc_span: int = 6
    # 同步参数
    cfo_search_range_hz: float = 5000.0
    cfo_search_step_hz: float = 100.0
    timing_damping: float = 0.707
    timing_loop_bw: float = 0.01
    # 滤波
    enable_notch: bool = False
    notch_frequency_hz: float = 0.0
    notch_bandwidth_hz: float = 0.0
    # FEC 迭代
    fec_max_iterations: int = 25
    # 帧检测阈值
    frame_detection_threshold: float = 0.1
    # 描述
    description: str = ""


@dataclass
class Prediction:
    """ML 预测结果。"""
    class_label: str = ""
    confidence: float = 0.0
    all_probs: dict[str, float] = field(default_factory=dict)
    is_ood: bool = False
    inference_time_ms: float = 0.0


@dataclass
class RxMetrics:
    """接收端实时指标。"""
    snr_db: float = float("nan")
    evm: float = float("nan")
    per: float = 0.0
    goodput_bps: float = 0.0
    sync_state: SyncState = SyncState.IDLE
    blocks_recovered: int = 0
    total_blocks: int = 0
    dropped_samples: int = 0
    buffer_depth: int = 0
    profile_active: ProfileID = ProfileID.P1_ROBUST


@dataclass
class AssemblyStatus:
    """文件组装状态。"""
    file_id: int = 0
    total_blocks: int = 0
    recovered_blocks: int = 0
    complete: bool = False
    bitmap: set[int] = field(default_factory=set)
    payload: bytearray = field(default_factory=bytearray)


# ── Competition-specific types ──────────────────────────────────


class TDDMode(str, Enum):
    """TDD operation mode."""
    CCA = "cca"
    TX = "tx"
    RX = "rx"
    GUARD = "guard"
    IDLE = "idle"


class FHStrategy(str, Enum):
    """Frequency hopping strategy."""
    SEQUENTIAL = "sequential"
    PSEUDO_RANDOM = "pseudo_random"
    ADAPTIVE = "adaptive"


@dataclass
class ContestConfigData:
    """Competition configuration data (serializable)."""
    team_id: int = 0
    file_id: int = 0
    spreading_factor: int = 128
    block_size_bytes: int = 256
    tdd_superframe_s: float = 0.200
    cca_threshold_db: float = -70.0
    hop_channels: list[float] = field(default_factory=list)
    center_frequency_hz: float = 2.45e9
    sample_rate_hz: float = 2.0e6
    rf_bandwidth_hz: float = 2.0e6
    tx_gain_db: float = -10.0
    rx_gain_db: float = 40.0
    channel_blacklist_timeout_s: float = 5.0
    fountain_block_size: int = 256
    sim_mode: bool = False

    def validate(self) -> list[str]:
        issues = []
        if self.spreading_factor < 8:
            issues.append(f"spreading_factor too small: {self.spreading_factor}")
        if self.spreading_factor > 4096:
            issues.append(f"spreading_factor too large: {self.spreading_factor}")
        if self.sample_rate_hz < 100e3:
            issues.append(f"sample_rate_hz too low: {self.sample_rate_hz}")
        if self.sample_rate_hz > 61.44e6:
            issues.append(f"sample_rate_hz exceeds PlutoSDR limit")
        return issues


@dataclass
class TransmissionReport:
    """Post-transmission report."""
    file_path: str = ""
    file_size_bytes: int = 0
    total_blocks: int = 0
    packets_sent: int = 0
    transmission_time_s: float = 0.0
    goodput_bps: float = 0.0
    frequencies_used: list[float] = field(default_factory=list)
    cca_busy_count: int = 0
    success: bool = False
    error_message: str = ""


@dataclass
class ReceptionReport:
    """Post-reception report."""
    output_path: str = ""
    bytes_recovered: int = 0
    bytes_expected: int = 0
    packets_received: int = 0
    packets_unique: int = 0
    reception_time_s: float = 0.0
    goodput_bps: float = 0.0
    fountain_overhead_pct: float = 0.0
    checksum_match: bool = False
    success: bool = False
    error_message: str = ""
