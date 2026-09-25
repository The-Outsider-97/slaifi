"""Structured logging built only on the Python standard library."""

import json
import logging
from datetime import UTC, datetime
from typing import Any

_CONTEXT_FIELDS = (
    "component",
    "operation",
    "asset",
    "portfolio_id",
    "calculation_id",
    "model_version",
)


class JsonFormatter(logging.Formatter):
    """Emit one compact JSON object per log record."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in _CONTEXT_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)


def configure_logging(level: str, *, force: bool = False) -> None:
    """Configure standalone logging while preserving an embedding host by default."""

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(
        level=level.upper(),
        handlers=[handler],
        force=force,
    )
