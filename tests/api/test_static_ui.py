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


def test_hashed_files_are_cached_for_good_and_the_page_itself_is_always_rechecked(
    tmp_path: Path,
) -> None:
    dist = _build_fake_dist(tmp_path)
    (dist / "assets" / "index-Bq3x9KdA.js").write_text("console.log('hashed')", encoding="utf-8")
    with _client(tmp_path, dist) as client:
        hashed = client.get("/assets/index-Bq3x9KdA.js")
        assert hashed.headers["cache-control"] == "private, max-age=31536000, immutable"
        # A file whose name does not change with its content must never be kept for a year; it
        # gets no caching rule of its own (the access middleware then answers ``no-store``).
        for path in ("/assets/app.js", "/", "/some/client/route"):
            assert "max-age" not in client.get(path).headers.get("cache-control", ""), path


def test_large_replies_are_compressed_and_small_ones_are_left_alone(tmp_path: Path) -> None:
    dist = _build_fake_dist(tmp_path)
    (dist / "assets" / "big-Zk29fjQp.js").write_text("const a = 1;\n" * 2000, encoding="utf-8")
    with _client(tmp_path, dist) as client:
        big = client.get("/assets/big-Zk29fjQp.js", headers={"Accept-Encoding": "gzip"})
        assert big.headers["content-encoding"] == "gzip"
        assert int(big.headers["content-length"]) < 2000  # 26,000 bytes of text
        assert big.text.startswith("const a = 1;")  # the client still reads the original
        small = client.get("/health", headers={"Accept-Encoding": "gzip"})
        assert "content-encoding" not in small.headers
        plain = client.get("/assets/big-Zk29fjQp.js", headers={"Accept-Encoding": "identity"})
        assert "content-encoding" not in plain.headers
