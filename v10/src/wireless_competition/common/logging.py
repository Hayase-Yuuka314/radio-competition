"""结构化日志模块。

日志包含时间、版本、配置哈希和种子，便于追溯。
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional


# 全局 logger 名称
LOGGER_NAME = "wireless_competition"

# 版本标识
VERSION = "0.1.0"


def _create_formatter(verbose: bool = False) -> logging.Formatter:
    """创建日志格式化器。"""
    if verbose:
        fmt = (
            "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s"
        )
    else:
        fmt = "%(asctime)s | %(levelname)-8s | %(message)s"
    return logging.Formatter(fmt, datefmt="%Y-%m-%dT%H:%M:%S")


def setup(
    level: int = logging.INFO,
    log_file: Optional[str | Path] = None,
    verbose: bool = False,
    force: bool = False,
) -> logging.Logger:
    """配置并返回主 logger。

    Args:
        level: 日志级别。
        log_file: 可选日志文件路径。
        verbose: 是否在日志中包含模块/函数/行号。
        force: 是否强制重新配置（清除已有 handler）。

    Returns:
        配置好的 Logger 实例。
    """
    logger = logging.getLogger(LOGGER_NAME)

    if force:
        logger.handlers.clear()

    if logger.handlers:
        return logger

    logger.setLevel(level)

    # 控制台 handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(_create_formatter(verbose))
    logger.addHandler(console)

    # 文件 handler
    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(_create_formatter(verbose=True))
        logger.addHandler(file_handler)

    return logger


def get_logger() -> logging.Logger:
    """获取主 logger。如未配置则使用默认配置。"""
    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        return setup()
    return logger


def log_context(
    logger: logging.Logger,
    git_commit: str = "unknown",
    config_hash: str = "unknown",
    seed: int = 0,
) -> None:
    """记录运行上下文。"""
    logger.info("=" * 60)
    logger.info(f"Wireless Competition v{VERSION}")
    logger.info(f"Git commit: {git_commit}")
    logger.info(f"Config hash: {config_hash}")
    logger.info(f"Base seed: {seed}")
    logger.info("=" * 60)
