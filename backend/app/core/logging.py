import logging
import sys
from pathlib import Path

from app.core.config import get_settings


def setup_logging() -> None:
    settings = get_settings()
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    if root_logger.handlers:
        return

    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    try:
        log_file = Path(settings.log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(settings.log_file, encoding="utf-8")
        file_formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
    except Exception as e:
        root_logger.warning("无法创建日志文件: %s", str(e))

    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    root_logger.info("日志系统初始化完成，日志级别: %s", settings.log_level)
