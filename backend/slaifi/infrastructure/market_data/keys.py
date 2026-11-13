"""Market-data API keys saved from Settings.

A key typed into Settings is kept in one small file in SLAIFI's own data folder (written with SLAI's
atomic writer, readable by the current user only on systems that support it), never in the ledger, the
audit log, a response or a log line. A saved key takes precedence over the same key in ``.env``;
removing it falls back to ``.env``.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import threading
from collections.abc import Callable
from pathlib import Path

import httpx

from slaifi.core.config import Settings
from slaifi.core.utils.errors import ValidationError
from slaifi.domain.market import ProviderKeyInfo
from slaifi.infrastructure.market_data.factory import KEY_ENV, PROVIDER_CLASSES, build_provider
from slaifi.infrastructure.market_data.gateway import MultiSourceGateway

MAX_KEY_LENGTH = 256
_KEY_PATTERN = re.compile(r"^[\x21-\x7e]+$")  # visible ASCII, no spaces


def clean_key(raw: str) -> str:
    """The key as it will be stored, or a plain-words error (the key itself is never echoed)."""

    key = (raw or "").strip()
    if key.lower().startswith("bearer "):
        key = key[7:].strip()
    if not key:
        raise ValidationError("Paste the API key first; the box is empty.")
    if len(key) > MAX_KEY_LENGTH:
        raise ValidationError(
            f"That is too long for an API key (more than {MAX_KEY_LENGTH} characters)."
        )
    if not _KEY_PATTERN.match(key):
        raise ValidationError(
            "An API key has no spaces or special characters; check that you copied only the key."
        )
    return key


class ProviderKeyStore:
    """The saved keys, kept in memory and in one JSON file."""

    def __init__(
        self, path: Path, fallback: Callable[[str], str | None] = lambda name: None
    ) -> None:
        self._path = path
        self._fallback = fallback  # the key from .env / the environment
        self._lock = threading.Lock()
        self._keys: dict[str, str] = self._read()

    def _read(self) -> dict[str, str]:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(raw, dict):
            return {}
        return {
            name: key
            for name, key in raw.items()
            if name in PROVIDER_CLASSES and isinstance(key, str) and key.strip()
        }

    def get(self, name: str) -> str | None:
        with self._lock:
            return self._keys.get(name)

    def resolve(self, name: str) -> str | None:
        """The key to use: the one saved in Settings, else the one from ``.env``."""

        return self.get(name) or self._fallback(name)

    def names(self) -> frozenset[str]:
        with self._lock:
            return frozenset(self._keys)

    def _write(self) -> None:
        from applications.tools.storage import atomic_write_json  # SLAI's atomic writer

        atomic_write_json(self._path, self._keys)
        with contextlib.suppress(
            OSError
        ):  # not supported on every file system; the folder is the user's own
            os.chmod(self._path, 0o600)

    def set(self, name: str, key: str) -> None:
        with self._lock:
            previous = self._keys.get(name)
            self._keys[name] = key
            try:
                self._write()
            except Exception:
                if previous is None:
                    self._keys.pop(name, None)
                else:
                    self._keys[name] = previous
                raise

    def delete(self, name: str) -> None:
        with self._lock:
            previous = self._keys.pop(name, None)
            if previous is None:
                return
            try:
                self._write()
            except Exception:
                self._keys[name] = previous
                raise


class ProviderKeyManager:
    """Applies a saved or removed key to the running gateway, without a restart."""

    def __init__(
        self,
        gateway: MultiSourceGateway,
        settings: Settings,
        store: ProviderKeyStore,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._gateway = gateway
        self._settings = settings
        self._store = store
        self._transport = transport

    def _source(self, name: str) -> str | None:
        if name in self._store.names():
            return "settings"
        return "environment" if self._settings.provider_key(name) else None

    def _info(self, name: str) -> ProviderKeyInfo:
        return ProviderKeyInfo(
            name, PROVIDER_CLASSES[name].label, KEY_ENV[name], self._source(name)
        )

    def info(self) -> tuple[ProviderKeyInfo, ...]:
        return tuple(self._info(name) for name in self._settings.provider_order)

    def _require(self, name: str) -> str:
        if name not in self._settings.provider_order:
            raise ValidationError(f"Unknown market-data source {name!r}.")
        return name

    async def _apply(self, changed: str) -> None:
        """Rebuild only the changed adapter; the others keep their budgets and health."""

        keep = {p.name: p for p in self._gateway.providers}
        configured: list[object] = []
        missing: list[type] = []
        for name in self._settings.provider_order:
            key = self._store.resolve(name)
            if key is None:
                missing.append(PROVIDER_CLASSES[name])
            elif name != changed and name in keep:
                configured.append(keep[name])
            else:
                configured.append(
                    build_provider(name, key, self._settings, transport=self._transport)
                )
        await self._gateway.replace_providers(configured, missing)  # type: ignore[arg-type]

    async def set_key(self, name: str, key: str) -> ProviderKeyInfo:
        name = self._require(name)
        cleaned = clean_key(key)
        previous = self._store.get(name)
        self._store.set(name, cleaned)
        try:
            await self._apply(name)
        except Exception:
            if previous is None:
                self._store.delete(name)
            else:
                self._store.set(name, previous)
            raise
        return self._info(name)

    async def clear_key(self, name: str) -> ProviderKeyInfo:
        name = self._require(name)
        self._store.delete(name)
        await self._apply(name)
        return self._info(name)
