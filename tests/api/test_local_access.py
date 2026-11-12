"""The local-access rules every SLAI application follows: token -> cookie, Host/Origin, headers."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from slaifi.core.config import Settings
from slaifi.main import create_app

PORT = 8777
TOKEN = "t0ken-for-tests-0123456789"
HEADERS = {"Content-Security-Policy": "default-src 'none'", "X-Content-Type-Options": "nosniff"}


def _dist(root: Path) -> Path:
    dist = root / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>SLAIFI</title>", encoding="utf-8")
    return dist


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(
        environment="test",
        slai_enabled=False,
        data_dir=tmp_path / "data",
        api_port=PORT,
        frontend_dist_dir=_dist(tmp_path),
    )
    app = create_app(settings, access_token=TOKEN, security_headers=HEADERS)
    with TestClient(app, base_url=f"http://127.0.0.1:{PORT}", follow_redirects=False) as c:
        yield c


def test_no_cookie_means_no_data(client: TestClient) -> None:
    api = client.get("/api/v1/system/status")
    assert api.status_code == 401 and TOKEN not in api.text
    page = client.get("/")
    assert page.status_code == 403 and "needs the link" in page.text and TOKEN not in page.text


def test_token_is_traded_once_for_an_httponly_strict_cookie(client: TestClient) -> None:
    wrong = client.get("/", params={"token": "nope"})
    assert wrong.status_code == 403 and "set-cookie" not in wrong.headers
    ok = client.get("/", params={"token": TOKEN})
    assert ok.status_code == 302 and ok.headers["location"] == "/"
    cookie = ok.headers["set-cookie"]
    assert (
        cookie.startswith("slai_slaifi_token=")
        and "HttpOnly" in cookie
        and "SameSite=Strict" in cookie
    )
    # With the cookie the UI and the API answer; the redirect target is the clean URL.
    assert "<title>SLAIFI</title>" in client.get("/").text
    assert client.get("/api/v1/system/status").status_code == 200


def test_wrong_cookie_is_refused(client: TestClient) -> None:
    client.cookies.set("slai_slaifi_token", "forged")
    assert client.get("/api/v1/system/status").status_code == 401


def test_other_hosts_are_refused_even_with_the_cookie(client: TestClient) -> None:
    client.get("/", params={"token": TOKEN})
    rebound = client.get("/api/v1/system/status", headers={"Host": "evil.example:8777"})
    assert rebound.status_code == 401


def test_changes_from_another_origin_are_refused(client: TestClient) -> None:
    client.get("/", params={"token": TOKEN})
    foreign = client.post(
        "/api/v1/system/backup", headers={"Origin": "http://evil.example", "X-SLAIFI-Client": "web"}
    )
    assert foreign.status_code == 403
    same = client.post(
        "/api/v1/system/backup",
        headers={"Origin": f"http://127.0.0.1:{PORT}", "X-SLAIFI-Client": "web"},
    )
    assert same.status_code == 200


def test_security_headers_are_on_every_answer(client: TestClient) -> None:
    for response in (
        client.get("/"),
        client.get("/", params={"token": TOKEN}),
        client.get("/api/v1/x"),
    ):
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["content-security-policy"] == "default-src 'none'"
        assert response.headers["cache-control"] == "no-store"
    client.get("/", params={"token": TOKEN})
    assert client.get("/api/v1/system/status").headers["x-content-type-options"] == "nosniff"


def test_without_a_token_the_app_is_open_for_tests_and_uvicorn(tmp_path: Path) -> None:
    settings = Settings(environment="test", slai_enabled=False, data_dir=tmp_path / "d")
    with TestClient(create_app(settings)) as plain:
        assert plain.get("/health").json() == {"status": "ok"}
