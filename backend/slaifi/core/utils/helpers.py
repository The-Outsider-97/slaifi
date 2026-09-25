"""Finance-agnostic helpers shared across SLAIFI higher layers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any


def is_aware_datetime(value: datetime) -> bool:
    """Return whether a datetime identifies an absolute instant."""

    return value.tzinfo is not None and value.utcoffset() is not None


def to_json_safe(value: Any) -> Any:
    """Recursively convert common immutable/runtime values to JSON-safe data.

    The helper intentionally does not call ``json.dumps`` and does not impose an
    API schema. It is suitable for integration envelopes, diagnostic context,
    and other higher-layer serialization boundaries.
    """

    if is_dataclass(value) and not isinstance(value, type):
        return to_json_safe(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): to_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_json_safe(item) for item in value]
    if isinstance(value, Enum):
        return to_json_safe(value.value)
    if isinstance(value, (datetime, Decimal)):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
