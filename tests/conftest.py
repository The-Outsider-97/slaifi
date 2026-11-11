"""Shared fixtures. Tests never touch the real SLAI data folder."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "slaifi-data"
    monkeypatch.setenv("SLAIFI_DATA_DIR", str(data_dir))
    from slaifi.core.config import get_settings

    get_settings.cache_clear()
    return data_dir
