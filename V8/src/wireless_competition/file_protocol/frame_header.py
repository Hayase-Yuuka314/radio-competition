"""帧头构造与解析。

帧头使用固定强健调制与编码，携带协议版本和有效载荷参数。
字段布局（字节）：
  [0]      protocol_version
  [1]      file_id (高字节)
  [2]      file_id (低字节)
  [3]      session_id
  [4-5]    block_sequence (uint16 big-endian)
  [6-7]    total_blocks (uint16 big-endian)
  [8-9]    payload_length (uint16 big-endian)
  [10]     profile_id
  [11]     repetition_id
  [12-13]  header_crc (uint16 big-endian, CRC-CCITT of bytes 0-11)
"""

from __future__ import annotations

import struct

from ..common.types import FailureReason, FrameMetadata, ProfileID


HEADER_LENGTH_BYTES = 14          # 含 CRC
HEADER_PAYLOAD_BYTES = 12        # 不含 CRC 的包头


def compute_header_crc16(header_bytes: bytes) -> int:
    """计算包头 CRC-CCITT (0xFFFF)。

    使用多项式 0x1021，初始值 0xFFFF，不反射。
    """
    crc = 0xFFFF
    for b in header_bytes:
        crc ^= (b << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def encode_header(metadata: FrameMetadata) -> bytes:
    """编码帧元数据到头字节序列。

    Args:
        metadata: 帧元数据。

    Returns:
        14 字节帧头。
    """
    profile_map = {
        ProfileID.P0_RESCUE: 0,
        ProfileID.P1_ROBUST: 1,
        ProfileID.P2_BALANCED: 2,
        ProfileID.P3_FAST: 3,
        ProfileID.P4_NOTCH: 4,
        ProfileID.P5_BURST: 5,
    }
    profile_byte = profile_map.get(metadata.profile_id, 2)

    payload = struct.pack(
        ">BBBBHHHBB",
        metadata.protocol_version & 0xFF,
        (metadata.file_id >> 8) & 0xFF,
        metadata.file_id & 0xFF,
        metadata.session_id & 0xFF,
        metadata.block_sequence & 0xFFFF,
        metadata.total_blocks & 0xFFFF,
        metadata.payload_length & 0xFFFF,
        profile_byte,
        metadata.repetition_id & 0xFF,
    )
    crc = compute_header_crc16(payload)
    return payload + struct.pack(">H", crc)


def decode_header(header_bytes: bytes) -> FrameMetadata:
    """解析帧头字节序列。

    Args:
        header_bytes: 14 字节帧头。

    Returns:
        FrameMetadata 实例。

    Raises:
        ValueError: 如果帧头长度不正确。
    """
    if len(header_bytes) < HEADER_LENGTH_BYTES:
        raise ValueError(
            f"Header too short: {len(header_bytes)} < {HEADER_LENGTH_BYTES}"
        )

    payload = header_bytes[:HEADER_PAYLOAD_BYTES]
    crc_received = struct.unpack(">H", header_bytes[HEADER_PAYLOAD_BYTES:HEADER_LENGTH_BYTES])[0]
    crc_computed = compute_header_crc16(payload)

    (
        protocol_version,
        file_id_hi,
        file_id_lo,
        session_id,
        block_sequence,
        total_blocks,
        payload_length,
        profile_byte,
        repetition_id,
    ) = struct.unpack(">BBBBHHHBB", payload)

    file_id = (file_id_hi << 8) | file_id_lo

    profile_map = {
        0: ProfileID.P0_RESCUE,
        1: ProfileID.P1_ROBUST,
        2: ProfileID.P2_BALANCED,
        3: ProfileID.P3_FAST,
        4: ProfileID.P4_NOTCH,
        5: ProfileID.P5_BURST,
    }
    profile_id = profile_map.get(profile_byte, ProfileID.P2_BALANCED)

    meta = FrameMetadata(
        protocol_version=protocol_version,
        file_id=file_id,
        session_id=session_id,
        block_sequence=block_sequence,
        total_blocks=total_blocks,
        payload_length=payload_length,
        profile_id=profile_id,
        repetition_id=repetition_id,
        header_crc=crc_computed,
    )

    if crc_received != crc_computed:
        # 标记为 CRC 失败但仍在 metadata 中保留解析结果供诊断
        meta.header_crc = crc_computed

    return meta, crc_received == crc_computed


def validate_header(meta: FrameMetadata) -> list[str]:
    """校验帧头的字段合法性。

    Returns:
        警告/错误列表。
    """
    issues: list[str] = []
    if meta.protocol_version < 1:
        issues.append(f"Invalid protocol_version: {meta.protocol_version}")
    if meta.total_blocks <= 0:
        issues.append(f"Invalid total_blocks: {meta.total_blocks}")
    if meta.block_sequence >= meta.total_blocks and meta.total_blocks > 0:
        issues.append(
            f"block_sequence ({meta.block_sequence}) >= total_blocks ({meta.total_blocks})"
        )
    return issues
