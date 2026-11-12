"""The API process can serve the built web UI, so one command starts everything."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from slaifi.core.config import Settings
from slaifi.main import create_app


def _client(tmp_path: Path, dist: Path | None) -> TestClient:
    settings = Settings(
        environment="test",
        slai_enabled=False,
        data_dir=tmp_path / "data",
        frontend_dist_dir=dist,
    )
    return TestClient(create_app(settings))


def _build_fake_dist(root: Path) -> Path:
    dist = root / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>SLAIFI</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('ui')", encoding="utf-8")
    return dist


def test_built_ui_is_served_and_api_routes_still_win(tmp_path: Path) -> None:
    dist = _build_fake_dist(tmp_path)
    with _client(tmp_path, dist) as client:
        index = client.get("/")
        assert index.status_code == 200 and "<title>SLAIFI</title>" in index.text
        assert client.get("/assets/app.js").text == "console.log('ui')"
        # Anything that is not a file falls back to the single-page app.
        assert "<title>SLAIFI</title>" in client.get("/some/client/route").text
        # API, health and docs are never shadowed by the UI.
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/api/v1/system/status").status_code == 200
        assert client.get("/openapi.json").status_code == 200


def test_missing_build_serves_no_ui_but_the_api_works(tmp_path: Path) -> None:
    with _client(tmp_path, tmp_path / "not-built") as client:
        assert client.get("/").status_code == 404
        assert client.get("/health").json() == {"status": "ok"}
