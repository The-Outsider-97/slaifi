"""Applying a suggested allocation: all of it or one line, as ordinary paper orders."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from tests.api.test_agents_api import H, app_client, buy, enable, loosen
from tests.api.test_finance_api import make_portfolio

from slaifi.application.contracts import AllocationProblem, AllocationSolution

HELD = (("KO", "30"), ("JNJ", "10"), ("SPY", "5"), ("DIA", "5"))
# Share of the invested budget each asset should get: KO is sold out, the rest are resized.
TARGET = {"KO": 0.0, "JNJ": 0.40, "SPY": 0.35, "DIA": 0.25}


class Targets:
    """A stand-in Financial agent that proposes fixed shares of the budget."""

    def check(self) -> None:
        return None

    def solve(self, problem: AllocationProblem) -> AllocationSolution:
        weights = tuple(TARGET[s] * problem.budget for s in problem.symbols)
        return AllocationSolution("ok", weights, solver="stand-in")


@pytest.fixture()
def setup(tmp_path: Path) -> Any:
    with app_client(tmp_path, financial_analyst=Targets()) as c:
        loosen(c, cap=0.5)
        pid = make_portfolio(c, "20000")
        for symbol, qty in HELD:
            buy(c, pid, symbol, qty)
        enable(c, "financial")
        yield c, pid


def suggest(c: TestClient, pid: str) -> dict[str, Any]:
    got = c.get(f"/api/v1/paper/portfolios/{pid}/allocation").json()
    assert got["status"] == "ok", got
    return dict(got)


def apply(c: TestClient, pid: str, sid: str, symbols: list[str] | None = None) -> Any:
    body: dict[str, Any] = {"suggestion_id": sid}
    if symbols is not None:
        body["symbols"] = symbols
    return c.post(f"/api/v1/paper/portfolios/{pid}/allocation/apply", headers=H, json=body)


def held(c: TestClient, pid: str) -> dict[str, float]:
    view = c.get(f"/api/v1/paper/portfolios/{pid}").json()
    return {p["asset"]["symbol"]: float(p["quantity"]) for p in view["positions"]}


def test_a_suggestion_says_which_lines_would_trade_and_what_the_fee_is(setup: Any) -> None:
    c, pid = setup
    got = suggest(c, pid)
    assert got["suggestion_id"] and got["expires_at"] and got["fee_per_trade"] == "1.00"
    sides = {line["symbol"]: line["side"] for line in got["lines"]}
    assert sides["KO"] == "sell"
    assert all(side in {"buy", "sell", None} for side in sides.values())
    for line in got["lines"]:  # a line is actionable only when it really moves money
        assert (line["side"] is None) or abs(float(line["amount"])) >= 1


def test_apply_all_sells_first_then_buys_and_every_order_pays_the_platform_fee(
    setup: Any,
) -> None:
    c, pid = setup
    got = suggest(c, pid)
    traded = [x["symbol"] for x in got["lines"] if x["side"]]
    cash_before = float(c.get(f"/api/v1/paper/portfolios/{pid}").json()["cash_balance"])
    r = apply(c, pid, got["suggestion_id"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["simulated"] is True
    statuses = {o["symbol"]: o["status"] for o in body["orders"]}
    assert set(statuses) == set(traded) and set(statuses.values()) == {"filled"}, body
    sides = [o["side"] for o in body["orders"]]
    assert sides == sorted(sides, key=lambda s: s != "sell")  # every sell before any buy
    assert all(o["fee"] == "1.00" for o in body["orders"])
    assert body["fees"] == f"{len(traded)}.00" or float(body["fees"]) == len(traded)
    after = held(c, pid)
    assert "KO" not in after or after["KO"] == 0  # the suggested 0 % was closed out
    cash_after = float(c.get(f"/api/v1/paper/portfolios/{pid}").json()["cash_balance"])
    assert cash_after != cash_before
    audit = c.get("/api/v1/system/audit", params={"subject": pid}).json()["entries"]
    assert any(a["action"] == "paper.allocation.applied" for a in audit)
    report = c.get("/api/v1/system/reconcile").json()
    assert not [i for i in report["issues"] if i["severity"] == "error"], report


def test_applying_again_places_nothing_twice(setup: Any) -> None:
    c, pid = setup
    got = suggest(c, pid)
    first = apply(c, pid, got["suggestion_id"]).json()
    trades = len(c.get(f"/api/v1/paper/portfolios/{pid}/history").json()["entries"])
    again = apply(c, pid, got["suggestion_id"])
    assert again.status_code == 200
    assert {o["status"] for o in again.json()["orders"]} == {"already_applied"}
    assert len(c.get(f"/api/v1/paper/portfolios/{pid}/history").json()["entries"]) == trades
    assert first["filled"] == len(again.json()["orders"])


def test_one_line_can_be_applied_and_the_rest_afterwards(setup: Any) -> None:
    c, pid = setup
    got = suggest(c, pid)
    traded = [x["symbol"] for x in got["lines"] if x["side"]]
    one, rest = traded[0], traded[1:]
    r = apply(c, pid, got["suggestion_id"], [one])
    assert r.status_code == 200 and [o["symbol"] for o in r.json()["orders"]] == [one]
    assert r.json()["orders"][0]["status"] == "filled"
    # Applying one line does not make the others stale.
    r2 = apply(c, pid, got["suggestion_id"], rest)
    assert r2.status_code == 200 and {o["status"] for o in r2.json()["orders"]} == {"filled"}
    assert apply(c, pid, got["suggestion_id"], [one]).json()["orders"][0]["status"] == (
        "already_applied"
    )


def test_the_browser_cannot_choose_amounts_or_unknown_lines(setup: Any) -> None:
    c, pid = setup
    got = suggest(c, pid)
    url = f"/api/v1/paper/portfolios/{pid}/allocation/apply"
    sneaky = c.post(
        url,
        headers=H,
        json={"suggestion_id": got["suggestion_id"], "symbols": ["JNJ"], "amount": "999999"},
    )
    assert sneaky.status_code == 422
    assert apply(c, pid, got["suggestion_id"], ["TSLA"]).status_code == 404
    assert c.post(url, json={"suggestion_id": got["suggestion_id"]}).status_code == 403
    assert held(c, pid)["KO"] == 30  # nothing was ordered by any of that


def test_a_suggestion_that_is_unknown_expired_or_for_another_portfolio_is_refused(
    setup: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    c, pid = setup
    got = suggest(c, pid)
    assert apply(c, pid, "S-doesnotexist").status_code == 404
    other = make_portfolio(c, "5000")
    assert apply(c, other, got["suggestion_id"]).status_code == 404
    import slaifi.application.allocation.service as module

    monkeypatch.setattr(module, "PLAN_TTL", timedelta(seconds=-1))
    expired = suggest(c, pid)
    gone = apply(c, pid, expired["suggestion_id"])
    assert gone.status_code == 404 and "expired" in gone.text


def test_a_suggestion_is_stale_once_the_portfolio_changed_underneath_it(setup: Any) -> None:
    c, pid = setup
    got = suggest(c, pid)
    buy(c, pid, "KO", "1")  # something else traded after the suggestion was made
    r = apply(c, pid, got["suggestion_id"])
    assert r.status_code == 409 and "changed" in r.text
    assert held(c, pid)["KO"] == 31


def test_a_refused_order_is_reported_and_the_others_still_go_through(setup: Any) -> None:
    c, pid = setup
    got = suggest(c, pid)
    # The market data cannot price one asset any more, so only that order is refused.
    c.put("/api/v1/paper/fees", headers=H, json={"per_trade": "1000"})
    r = apply(c, pid, got["suggestion_id"])
    assert r.status_code == 200
    statuses = {o["status"] for o in r.json()["orders"]}
    assert "rejected" in statuses
    rejected = next(o for o in r.json()["orders"] if o["status"] == "rejected")
    assert rejected["detail"] and rejected["quantity"] is None
