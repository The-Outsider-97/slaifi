"""Port for the market-data API keys a person can save in Settings (instead of, or beside, ``.env``)."""

from __future__ import annotations

from typing import Protocol

from slaifi.domain.market import ProviderKeyInfo


class ProviderKeys(Protocol):
    def info(self) -> tuple[ProviderKeyInfo, ...]: ...

    async def set_key(self, name: str, key: str) -> ProviderKeyInfo: ...

    async def clear_key(self, name: str) -> ProviderKeyInfo: ...
