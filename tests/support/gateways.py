"""Gateway builders for tests."""

from __future__ import annotations

from typing import Any

from tests.support.synthetic_feed import SyntheticFeed

from slaifi.infrastructure.market_data import InMemoryMarketCache
from slaifi.infrastructure.market_data.gateway import MultiSourceGateway


def synthetic_gateway(feed: SyntheticFeed | None = None, **kwargs: Any) -> MultiSourceGateway:
    """A real MultiSourceGateway over the deterministic test feed (no network, no keys)."""

    kwargs.setdefault("cache", InMemoryMarketCache())
    kwargs.setdefault("quote_ttl_seconds", 0.0)
    kwargs.setdefault("history_ttl_seconds", 0.0)
    return MultiSourceGateway([feed or SyntheticFeed()], **kwargs)  # type: ignore[list-item]
