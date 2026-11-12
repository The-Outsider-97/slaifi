"""``python -m applications.slaifi``: same start-up shape as the other SLAI applications.

These tests need the SLAI host (``applications.tools``); they are skipped where it is absent.
"""

from __future__ import annotations

import socket
import threading
from pathlib import Path
from typing import Any

import httpx
import pytest

pytest.importorskip("applications.tools.server")

from slaifi import launcher  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _built_ui(root: Path) -> Path:
    dist = root / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>SLAIFI</title>", encoding="utf-8")
    return dist


def test_configuration_precedence_file_then_env_then_command_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key in ("SLAIFI_API_PORT", "SLAIFI_MARKET_QUOTE_CACHE_TTL_SECONDS"):
        monkeypatch.delenv(key, raising=False)
    config = tmp_path / "config.yaml"
    config.write_text(
        "app:\n  port: 8801\n  market_quote_cache_ttl_seconds: 11\n  log_level: WARNING\n",
        encoding="utf-8",
    )
    env_file = tmp_path / ".env"
    env_file.write_text(
        "SLAIFI_MARKET_QUOTE_CACHE_TTL_SECONDS=22\nOTHER_SECRET=keep-out\n", encoding="utf-8"
    )

    settings, _path, _note = launcher.load_settings(
        config=str(config),
        data_dir=str(tmp_path / "d"),
        client_dir=None,
        port=None,
        env_file=env_file,
    )
    assert settings.api_port == 8801  # config.yaml
    assert settings.log_level == "WARNING"
    assert settings.market_quote_cache_ttl_seconds == 22  # .env beats config.yaml
    assert settings.data_dir == tmp_path / "d"

    monkeypatch.setenv("SLAIFI_MARKET_QUOTE_CACHE_TTL_SECONDS", "33")
    settings, _p, _n = launcher.load_settings(
        config=str(config), data_dir=None, client_dir=None, port=8802, env_file=env_file
    )
    assert settings.market_quote_cache_ttl_seconds == 33  # real environment beats .env
    assert settings.api_port == 8802  # command line beats config.yaml


def test_an_invalid_setting_names_the_setting(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("app:\n  port: 99999999\n", encoding="utf-8")
    with pytest.raises(ValueError, match="port"):
        launcher.load_settings(
            config=str(config), data_dir=None, client_dir=None, port=None, env_file=None
        )


def test_a_taken_port_is_refused_not_shared() -> None:
    first = launcher.bind("127.0.0.1", 0)
    try:
        with pytest.raises(OSError):
            launcher.bind("127.0.0.1", first.getsockname()[1])
    finally:
        first.close()


def test_remote_hosts_and_a_missing_client_are_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert launcher.main(["--host", "0.0.0.0", "--no-browser"]) == 2
    assert "non-loopback" in capsys.readouterr().err
    code = launcher.main(
        [
            "--client-dir",
            str(tmp_path / "nothing"),
            "--data-dir",
            str(tmp_path / "d"),
            "--no-browser",
        ]
    )
    assert code == 2 and "not built" in capsys.readouterr().err


def test_started_through_the_launcher_it_follows_the_shared_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for key in (
        "SLAIFI_API_PORT",
        "SLAIFI_TWELVEDATA_API_KEY",
        "SLAIFI_TIINGO_API_KEY",
        "SLAIFI_FMP_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("SLAIFI_FINNHUB_API_KEY", "super-secret-key-value")
    port = _free_port()
    seen: dict[str, Any] = {}

    def fake_serve(server: Any, **kw: Any) -> int:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        for _ in range(200):
            if server._server.started:
                break
            threading.Event().wait(0.05)
        try:
            base = f"http://127.0.0.1:{port}"
            with httpx.Client(base_url=base, follow_redirects=False) as c:
                seen["no_cookie"] = c.get("/api/v1/system/status").status_code
                exchange = c.get("/", params={"token": "fixed-token"})
                seen["exchange"] = (exchange.status_code, exchange.headers.get("location"))
                seen["with_cookie"] = c.get("/api/v1/system/status").status_code
                seen["ui"] = "SLAIFI" in c.get("/").text
                seen["rebound"] = c.get(
                    "/api/v1/system/status", headers={"Host": "evil.example"}
                ).status_code
            seen["serve_kwargs"] = kw
        finally:
            server.shutdown()
            thread.join(timeout=10)
            server.server_close()
        return 0

    monkeypatch.setattr(launcher, "serve", fake_serve)
    code = launcher.main(
        [
            "--port",
            str(port),
            "--token",
            "fixed-token",
            "--data-dir",
            str(tmp_path / "data"),
            "--client-dir",
            str(_built_ui(tmp_path)),
            "--no-browser",
        ]
    )
    assert code == 0
    assert seen["no_cookie"] == 401
    assert seen["exchange"] == (302, "/")
    assert seen["with_cookie"] == 200 and seen["ui"] is True and seen["rebound"] == 401

    kw = seen["serve_kwargs"]
    assert kw["title"] == "SLAIFI" and kw["url"] == f"http://127.0.0.1:{port}/?token=fixed-token"
    banner = " ".join(f"{k}={v}" for k, v in kw["details"]) + " ".join(kw["notes"])
    assert "finnhub" in banner  # which sources are configured is shown ...
    assert (
        "super-secret-key-value" not in banner + capsys.readouterr().out
    )  # ... their keys never are
    assert (tmp_path / "data" / "slaifi.db").exists()
