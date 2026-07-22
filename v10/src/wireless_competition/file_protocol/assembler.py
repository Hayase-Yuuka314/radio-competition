"""文件重组器。

接收端维护文件恢复状态，支持去重、乱序和阶段性保存。
"""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Optional

from ..common.types import AssemblyStatus, DecodeResult


class FileAssembler:
    """文件重组器。

    管理多个文件的接收进度，处理去重和重组。
    """

    def __init__(self):
        self._files: dict[int, AssemblyStatus] = {}

    def accept(self, result: DecodeResult) -> Optional[AssemblyStatus]:
        """接收一个解码结果。

        Args:
            result: 解码结果（必须包含有效 metadata 和已通过 CRC 的 payload）。

        Returns:
            更新后的组装状态。若该块之前已接收，返回 None。
        """
        if not result.frame_detected:
            return None
        if not result.payload_crc_pass:
            return None
        if result.metadata is None:
            return None

        meta = result.metadata
        fid = meta.file_id

        if fid not in self._files:
            self._files[fid] = AssemblyStatus(
                file_id=fid,
                total_blocks=meta.total_blocks,
            )

        status = self._files[fid]

        # 去重
        if meta.block_sequence in status.bitmap:
            return None

        # 存储
        status.bitmap.add(meta.block_sequence)
        status.recovered_blocks = len(status.bitmap)

        # 更新 total_blocks（支持动态更新）
        if meta.total_blocks > status.total_blocks:
            status.total_blocks = meta.total_blocks

        # 检查完整性
        if status.recovered_blocks >= status.total_blocks:
            status.complete = True

        return status

    def accept_raw(
        self,
        file_id: int,
        block_seq: int,
        total_blocks: int,
        payload: bytes,
    ) -> Optional[AssemblyStatus]:
        """接受原始块数据（不需要完整 DecodeResult）。

        用于快速集成。
        """
        from ..common.types import DecodeResult, FailureReason

        result = DecodeResult(
            frame_detected=True,
            payload_crc_pass=True,
            metadata=None,  # 会在 accept 中检查但这里绕过
            payload_bytes=payload,
        )
        # 直接用内部逻辑
        if file_id not in self._files:
            self._files[file_id] = AssemblyStatus(
                file_id=file_id,
                total_blocks=total_blocks,
            )
        status = self._files[file_id]
        if block_seq in status.bitmap:
            return None
        status.bitmap.add(block_seq)
        status.recovered_blocks = len(status.bitmap)
        if status.recovered_blocks >= status.total_blocks:
            status.complete = True
        # 存储 payload
        if not hasattr(status, '_blocks'):
            status._blocks = {}
        status._blocks[block_seq] = payload
        return status

    def get_status(self, file_id: int) -> Optional[AssemblyStatus]:
        """获取指定文件的重组状态。"""
        return self._files.get(file_id)

    def get_missing(self, file_id: int) -> list[int]:
        """获取指定文件缺失的块序号列表。"""
        status = self._files.get(file_id)
        if status is None:
            return []
        return sorted(set(range(status.total_blocks)) - status.bitmap)

    def is_complete(self, file_id: int) -> bool:
        """检查文件是否已完整恢复。"""
        status = self._files.get(file_id)
        return status is not None and status.complete

    def progress_fraction(self, file_id: int) -> float:
        """获取恢复进度（0-1）。"""
        status = self._files.get(file_id)
        if status is None or status.total_blocks == 0:
            return 0.0
        return status.recovered_blocks / status.total_blocks

    def save_checkpoint(self, file_id: int, output_dir: str | Path) -> Path:
        """将恢复进度保存到文件。

        Args:
            file_id: 文件 ID。
            output_dir: 输出目录。

        Returns:
            检查点文件路径。
        """
        status = self._files.get(file_id)
        if status is None:
            raise ValueError(f"No file with id {file_id}")

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        cp = out / f"checkpoint_{file_id}.json"

        data = {
            "file_id": status.file_id,
            "total_blocks": status.total_blocks,
            "recovered_blocks": status.recovered_blocks,
            "complete": status.complete,
            "bitmap": sorted(status.bitmap),
        }
        with open(cp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return cp

    def load_checkpoint(self, checkpoint_path: str | Path) -> None:
        """从检查点文件恢复状态。"""
        with open(checkpoint_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        fid = data["file_id"]
        self._files[fid] = AssemblyStatus(
            file_id=fid,
            total_blocks=data["total_blocks"],
            recovered_blocks=data["recovered_blocks"],
            complete=data["complete"],
            bitmap=set(data["bitmap"]),
        )

    def clear(self) -> None:
        """清空所有状态。"""
        self._files.clear()
