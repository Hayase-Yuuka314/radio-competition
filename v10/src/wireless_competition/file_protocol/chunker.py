"""文件分块器。

将任意二进制文件按固定或可配置块长切分。
"""

from __future__ import annotations

import struct
from typing import Optional


def chunk_file(
    data: bytes,
    block_size: int = 256,
) -> list[bytes]:
    """将字节数据切分成固定大小的块。

    Args:
        data: 原始文件字节。
        block_size: 每块有效载荷字节数。

    Returns:
        字节块列表。最后一块可能不足 block_size。
    """
    if block_size <= 0:
        raise ValueError(f"block_size must be positive, got {block_size}")
    blocks = []
    for i in range(0, len(data), block_size):
        blocks.append(data[i : i + block_size])
    return blocks


def chunk_file_with_metadata(
    data: bytes,
    file_id: int,
    block_size: int = 256,
) -> list[tuple[int, int, int, bytes]]:
    """切分文件并附带序号元数据。

    Args:
        data: 原始文件字节。
        file_id: 文件标识。
        block_size: 每块有效载荷字节数。

    Returns:
        (file_id, block_seq, total_blocks, payload) 列表。
    """
    blocks = chunk_file(data, block_size)
    total = len(blocks)
    return [(file_id, i, total, b) for i, b in enumerate(blocks)]


def reassemble_file(
    blocks: dict[int, bytes],
    total_blocks: int,
    total_size: Optional[int] = None,
) -> bytes:
    """从块字典重组文件。

    Args:
        blocks: {block_seq: payload} 映射。
        total_blocks: 预期总块数。
        total_size: 可选预期总字节数（用于截断最后一块填充）。

    Returns:
        重组后的完整文件字节。

    Raises:
        ValueError: 如果缺失某些块。
    """
    missing = sorted(set(range(total_blocks)) - set(blocks.keys()))
    if missing:
        raise ValueError(
            f"Missing {len(missing)} blocks: {missing[:10]}{'...' if len(missing) > 10 else ''}"
        )

    result = bytearray()
    for i in range(total_blocks):
        result.extend(blocks[i])

    if total_size is not None and total_size < len(result):
        result = result[:total_size]

    return bytes(result)
