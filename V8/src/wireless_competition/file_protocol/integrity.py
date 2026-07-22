"""循环冗余校验 (CRC) 模块。

提供 CRC-32 (IEEE 802.3) 实现用于有效载荷完整性检查。
"""

from __future__ import annotations

import struct

import numpy as np


# CRC-32 查找表 (多项式 0xEDB88320, 即 0x04C11DB7 的反射)
_CRC32_TABLE: list[int] = []


def _make_crc32_table() -> list[int]:
    """生成 CRC-32 查找表。"""
    table = []
    for i in range(256):
        crc = i
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xEDB88320
            else:
                crc >>= 1
        table.append(crc)
    return table


# 惰性初始化
if not _CRC32_TABLE:
    _CRC32_TABLE = _make_crc32_table()


def crc32(data: bytes, initial: int = 0xFFFFFFFF) -> int:
    """计算 CRC-32。

    Args:
        data: 输入字节。
        initial: 初始 CRC 值（用于增量计算）。

    Returns:
        32 位 CRC 值（未异或最终值）。
    """
    crc = initial
    for byte in data:
        idx = (crc ^ byte) & 0xFF
        crc = _CRC32_TABLE[idx] ^ (crc >> 8)
    return crc


def crc32_finalize(crc: int) -> int:
    """返回最终 CRC-32 值（异或 0xFFFFFFFF）。"""
    return crc ^ 0xFFFFFFFF


def append_crc32(data: bytes) -> bytes:
    """在数据末尾追加 CRC-32。

    Returns:
        data + CRC-32 (4 字节，小端序)。
    """
    crc = crc32_finalize(crc32(data))
    return data + struct.pack("<I", crc)


def check_crc32(data_with_crc: bytes) -> tuple[bytes, bool]:
    """校验并移除末尾 CRC-32。

    Args:
        data_with_crc: 数据 + 4 字节 CRC。

    Returns:
        (原始数据, 是否通过校验)。
    """
    if len(data_with_crc) < 4:
        return b"", False
    payload = data_with_crc[:-4]
    crc_received = struct.unpack("<I", data_with_crc[-4:])[0]
    crc_computed = crc32_finalize(crc32(payload))
    return payload, crc_received == crc_computed


def crc8(data: bytes, poly: int = 0x07, initial: int = 0x00) -> int:
    """计算 CRC-8（用于包头轻量校验）。

    Args:
        data: 输入字节。
        poly: 生成多项式。
        initial: 初始值。

    Returns:
        8 位 CRC 值。
    """
    crc = initial
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ poly) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc
