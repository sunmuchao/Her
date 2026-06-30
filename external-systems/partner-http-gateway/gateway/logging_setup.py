from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import TextIO


class _GatewayLogFormatter(logging.Formatter):
    """Keep pipeline records as raw JSON lines while formatting normal logs."""

    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)s %(name)s %(message)s")
        self._pipeline_formatter = logging.Formatter("%(message)s")

    def format(self, record: logging.LogRecord) -> str:
        if record.name == "her.pipeline" or record.name.startswith("her.pipeline."):
            return self._pipeline_formatter.format(record)
        return super().format(record)


def _reset_logger_handlers(logger: logging.Logger) -> None:
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()


def _parse_level(level_name: str | None, default: str = "INFO") -> int:
    return getattr(logging, str(level_name or default).upper(), logging.INFO)


def configure_gateway_logging(
    *,
    log_level: str | None = None,
    pipeline_log_level: str | None = None,
    log_file: str | None = None,
    stream: TextIO | None = None,
) -> None:
    root_level_name = log_level or os.environ.get("PARTNER_GATEWAY_LOG_LEVEL") or "INFO"
    pipeline_level_name = pipeline_log_level or os.environ.get("HER_PIPELINE_LOG_LEVEL") or root_level_name
    formatter = _GatewayLogFormatter()

    root_logger = logging.getLogger()
    _reset_logger_handlers(root_logger)
    root_logger.setLevel(_parse_level(root_level_name))

    console_handler = logging.StreamHandler(stream or sys.stderr)
    console_handler.setLevel(logging.NOTSET)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    resolved_log_file = log_file or os.environ.get("PARTNER_GATEWAY_LOG_FILE")
    if resolved_log_file:
        log_path = Path(resolved_log_file).expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.NOTSET)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    pipeline_logger = logging.getLogger("her.pipeline")
    _reset_logger_handlers(pipeline_logger)
    pipeline_logger.setLevel(_parse_level(pipeline_level_name, default=root_level_name))
    pipeline_logger.propagate = True

    # Suppress DEBUG logs from third-party libraries (urllib3, redis, etc.)
    third_party_loggers = [
        "urllib3",
        "urllib3.connectionpool",
        "redis",
        "redis.connection",
    ]
    for logger_name in third_party_loggers:
        third_party_logger = logging.getLogger(logger_name)
        third_party_logger.setLevel(logging.WARNING)
