"""API keys typed into Settings: saved, used at once, remembered, removable, never shown."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from tests.providers.test_multi_provider_app import H, Network

from slaifi.core.config import Settings
from slaifi.infrastructure.market_data.keys import ProviderKeyStore, clean_key
from slaifi.main import create_app

KEY = "tdkey-ABC123.xyz_789"


def make(tmp: Path, net: Network, **kw: Any) -> TestClient:
    cfg = Settings(environment="test", data_dir=tmp / "d", slai_enabled=False, **kw)
    return TestClient(
        create_app(cfg, market_transport=httpx.MockTransport(net)), raise_server_exceptions=False
    )


def listing(c: TestClient) -> dict[str, dict[str, Any]]:
    return {k["name"]: k for k in c.get("/api/v1/system/provider-keys").json()["keys"]}


def test_nothing_is_configured_until_a_key_is_saved(tmp_path: Path) -> None:
    with make(tmp_path, Network()) as c:
        keys = listing(c)
        assert set(keys) == {"twelvedata", "tiingo", "fmp", "finnhub", "alphavantage"}
        assert all(k["configured"] is False and k["source"] is None for k in keys.values())
        assert keys["twelvedata"]["env_var"] == "SLAIFI_TWELVEDATA_API_KEY"


def test_a_saved_key_is_used_at_once_without_a_restart_and_is_never_echoed(tmp_path: Path) -> None:
    net = Network()
    with make(tmp_path, net) as c:
        assert (
            c.put("/api/v1/system/provider-keys/twelvedata", json={"key": KEY}).status_code == 403
        )
        saved = c.put("/api/v1/system/provider-keys/twelvedata", headers=H, json={"key": KEY})
        assert saved.status_code == 200, saved.text
        assert saved.json() == {
            "name": "twelvedata",
            "label": saved.json()["label"],
            "env_var": "SLAIFI_TWELVEDATA_API_KEY",
            "configured": True,
            "source": "settings",
        }
        status = {p["name"]: p for p in c.get("/api/v1/system/providers").json()["providers"]}
        assert status["twelvedata"]["configured"] is True

        # Only that source is asked, and it is asked with the new key.
        check = c.post(
            "/api/v1/system/providers/check", params={"provider": "twelvedata"}, headers=H
        )
        assert [x["name"] for x in check.json()["checks"]] == ["twelvedata"]
        assert check.json()["checks"][0]["ok"] is True, check.text
        assert len(net.seen) == 1 and net.seen[0].url.params.get("apikey") == KEY

        # Not in any answer, log-like record or the audit trail.
        audit = c.get("/api/v1/system/audit").text
        assert "market.key.saved" in audit and KEY not in audit
        for url in (
            "/api/v1/system/provider-keys",
            "/api/v1/system/providers",
            "/api/v1/system/status",
        ):
            assert KEY not in c.get(url).text


def test_the_key_is_remembered_after_a_restart_and_the_file_is_private(tmp_path: Path) -> None:
    with make(tmp_path, Network()) as c:
        c.put("/api/v1/system/provider-keys/tiingo", headers=H, json={"key": KEY})
    file = tmp_path / "d" / "provider_keys.json"
    assert json.loads(file.read_text()) == {"tiingo": KEY}
    if os.name == "posix":
        assert stat.S_IMODE(file.stat().st_mode) == 0o600
    with make(tmp_path, Network()) as again:
        assert listing(again)["tiingo"]["source"] == "settings"
        ready = {
            p["name"]: p["state"] for p in again.get("/api/v1/system/providers").json()["providers"]
        }
        assert ready["tiingo"] != "not_configured"


def test_removing_a_saved_key_falls_back_to_env_and_then_to_nothing(tmp_path: Path) -> None:
    with make(tmp_path / "a", Network(), fmp_api_key=SecretStr("envkey")) as c:
        assert listing(c)["fmp"]["source"] == "environment"
        c.put("/api/v1/system/provider-keys/fmp", headers=H, json={"key": KEY})
        assert listing(c)["fmp"]["source"] == "settings"
        back = c.delete("/api/v1/system/provider-keys/fmp", headers=H).json()
        assert back["source"] == "environment" and back["configured"] is True
        assert "market.key.removed" in c.get("/api/v1/system/audit").text
    with make(tmp_path / "b", Network()) as c:
        c.put("/api/v1/system/provider-keys/fmp", headers=H, json={"key": KEY})
        assert c.delete("/api/v1/system/provider-keys/fmp", headers=H).json()["configured"] is False
        assert c.delete("/api/v1/system/provider-keys/fmp", headers=H).json()["configured"] is False


def test_a_replaced_key_keeps_the_other_sources_budgets_and_health(tmp_path: Path) -> None:
    with make(tmp_path, Network()) as c:
        c.put("/api/v1/system/provider-keys/tiingo", headers=H, json={"key": KEY})
        gateway = c.app.state.market_data_provider  # type: ignore[attr-defined]
        tiingo = next(p for p in gateway.providers if p.name == "tiingo")
        c.put("/api/v1/system/provider-keys/fmp", headers=H, json={"key": KEY + "2"})
        assert next(p for p in gateway.providers if p.name == "tiingo") is tiingo
        assert {p.name for p in gateway.providers} == {"tiingo", "fmp"}


@pytest.mark.parametrize("bad", ["", "   ", "two words", "k" * 300, "ключ", "key\nline"])
def test_a_key_that_cannot_be_a_key_is_refused_in_plain_words_without_echoing_it(
    tmp_path: Path, bad: str
) -> None:
    with make(tmp_path, Network()) as c:
        r = c.put("/api/v1/system/provider-keys/twelvedata", headers=H, json={"key": bad})
        assert r.status_code in (400, 422), r.text
        if bad.strip():
            assert bad not in r.text
        assert listing(c)["twelvedata"]["configured"] is False


def test_an_unknown_source_is_refused(tmp_path: Path) -> None:
    with make(tmp_path, Network()) as c:
        assert c.put(
            "/api/v1/system/provider-keys/nope", headers=H, json={"key": KEY}
        ).status_code in (
            400,
            404,
            422,
        )


def test_keys_cannot_be_changed_when_the_gateway_is_supplied_from_outside(tmp_path: Path) -> None:
    from tests.api.test_finance_api import create_app as finance_app
    from tests.api.test_finance_api import settings

    with TestClient(finance_app(settings(tmp_path))) as c:
        assert (
            c.put(
                "/api/v1/system/provider-keys/twelvedata", headers=H, json={"key": KEY}
            ).status_code
            == 409
        )


def test_key_cleaning_and_store_edge_cases(tmp_path: Path) -> None:
    assert clean_key("  Bearer abc-123  ") == "abc-123"
    store = ProviderKeyStore(tmp_path / "k.json", lambda name: "env" if name == "fmp" else None)
    assert store.resolve("fmp") == "env" and store.resolve("tiingo") is None
    store.set("tiingo", "k1")
    assert ProviderKeyStore(tmp_path / "k.json").get("tiingo") == "k1"
    (tmp_path / "bad.json").write_text("{not json")
    assert ProviderKeyStore(tmp_path / "bad.json").names() == frozenset()
    (tmp_path / "odd.json").write_text(
        json.dumps({"tiingo": "ok", "bogus": "x", "fmp": 5, "finnhub": " "})
    )
    assert ProviderKeyStore(tmp_path / "odd.json").names() == frozenset({"tiingo"})
