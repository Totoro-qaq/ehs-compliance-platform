"""应用日志：控制台 + 文件双输出，格式含源码文件与行号。"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


class AppLogger:
    """封装根日志配置与常用 get_logger，避免各模块重复拼格式。"""

    _configured = False

    @classmethod
    def configure(
        cls,
        *,
        log_dir: str | Path,
        log_file: str,
        log_level: str = 'INFO',
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 5,
    ) -> None:
        if cls._configured:
            return

        level = getattr(logging, log_level.upper(), logging.INFO)
        root = logging.getLogger()
        root.setLevel(level)
        root.handlers.clear()

        # 时间 | 级别 | logger 名 | 源文件路径:行号 | 消息（异常时用 exception 可带堆栈）
        line_fmt = (
            '%(asctime)s | %(levelname)-8s | %(name)s | %(pathname)s:%(lineno)d | %(message)s'
        )
        date_fmt = '%Y-%m-%d %H:%M:%S'
        formatter = logging.Formatter(fmt=line_fmt, datefmt=date_fmt)

        console = logging.StreamHandler(sys.stdout)
        console.setLevel(level)
        console.setFormatter(formatter)

        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path / log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8',
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)

        root.addHandler(console)
        root.addHandler(file_handler)

        cls._configured = True

    @staticmethod
    def get_logger(name: str) -> logging.Logger:
        return logging.getLogger(name)


def configure_logging(
    *,
    log_dir: str,
    log_file: str,
    log_level: str = 'INFO',
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
) -> None:
    """项目启动时调用一次（如 FastAPI lifespan）。"""
    AppLogger.configure(
        log_dir=log_dir,
        log_file=log_file,
        log_level=log_level,
        max_bytes=max_bytes,
        backup_count=backup_count,
    )


def get_logger(name: str) -> logging.Logger:
    """各模块使用：get_logger(__name__)。"""
    return AppLogger.get_logger(name)
