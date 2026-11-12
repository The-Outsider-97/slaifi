"""Rejected input is explained in plain language that names the field."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from slaifi.api.validation import explain_errors
from slaifi.core.config import Settings
from slaifi.main import create_app

H = {"X-SLAIFI-Client": "test"}


def _client(tmp: Path) -> TestClient:
    return TestClient(
        create_app(Settings(environment="test", data_dir=tmp / "d", slai_enabled=False))
    )


def _goal(**over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"name": "Income", "target_amount": "100", "period": "monthly"}
    body.update(over)
    return body


def test_currency_word_in_money_field_is_explained(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        r = client.post("/api/v1/goal-tracker", json=_goal(starting_capital="USD"), headers=H)
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "validation_error"
    assert "Starting capital" in body["detail"]
    assert "“USD”" in body["detail"] and "plain number" in body["detail"]
    assert "valid decimal" not in body["detail"]
    assert body["fields"][0]["field"] == "starting_capital"


def test_bounds_and_missing_fields_name_the_field(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        r = client.post(
            "/api/v1/goal-tracker", json=_goal(target_amount="0", horizon_years=500), headers=H
        )
        missing = client.post("/api/v1/goal-tracker", json={}, headers=H)
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "Target amount must be greater than 0." in detail
    assert "Time horizon (years) cannot be more than 100." in detail
    assert "Name is required." in missing.json()["detail"]


def test_negative_and_precision_messages() -> None:
    out = explain_errors(
        [
            {"type": "greater_than_equal", "loc": ("body", "starting_capital"), "ctx": {"ge": 0}},
            {
                "type": "decimal_max_places",
                "loc": ("body", "amount"),
                "ctx": {"decimal_places": 2},
            },
            {"type": "extra_forbidden", "loc": ("body", "wat")},
        ]
    )
    assert "Starting capital cannot be negative." in out["detail"]
    assert "Amount can have at most 2 decimal places." in out["detail"]
    assert "Wat is not a setting" in out["detail"]
    assert [f["field"] for f in out["fields"]] == ["starting_capital", "amount", "wat"]


def test_unreadable_body_has_a_plain_message(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        r = client.post(
            "/api/v1/goal-tracker",
            content=b"{not json",
            headers={**H, "Content-Type": "application/json"},
        )
    assert r.status_code == 422
    assert "could not be read" in r.json()["detail"]
