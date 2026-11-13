"""The trading platform's flat fees: per trade and per withdrawal, changeable by the person."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from tests.api.test_finance_api import H, create_app, make_portfolio, settings

P = "/api/v1/paper"


@pytest.fixture()
def client(tmp_path: Path) -> Any:
    with TestClient(create_app(settings(tmp_path)), raise_server_exceptions=False) as c:
        yield c


def buy(c: TestClient, pid: str, cid: str = "o1", quantity: str = "5") -> dict[str, Any]:
    r = c.post(
        f"{P}/portfolios/{pid}/orders",
        headers=H,
        json={"symbol": "KO", "side": "buy", "quantity": quantity, "client_order_id": cid},
    )
    assert r.status_code == 200, r.text
    return dict(r.json())


def test_default_is_one_per_trade_and_one_per_withdrawal(client: TestClient) -> None:
    body = client.get(f"{P}/fees").json()
    assert (body["per_trade"], body["per_withdrawal"]) == ("1.00", "1.00")


def test_a_trade_costs_the_flat_fee_on_top_of_slippage(client: TestClient) -> None:
    pid = make_portfolio(client, "10000")
    outcome = buy(client, pid)
    execution = outcome["decision"]["execution"]
    assert execution["commission"] == "1.00"
    portfolio = client.get(f"{P}/portfolios/{pid}").json()
    assert portfolio["fees_paid"] == "1.00"
    gross = Decimal(execution["gross_amount"])
    assert Decimal(portfolio["cash_balance"]) == Decimal("10000") - gross - Decimal("1.00")


def test_changing_the_trade_fee_applies_to_the_next_trade(client: TestClient) -> None:
    pid = make_portfolio(client, "10000")
    saved = client.put(f"{P}/fees", headers=H, json={"per_trade": "4.50"})
    assert saved.status_code == 200 and saved.json()["per_trade"] == "4.50"
    assert saved.json()["per_withdrawal"] == "1.00"
    assert buy(client, pid)["decision"]["execution"]["commission"] == "4.50"
    # A preview shows the same cost before anything is recorded.
    preview = client.post(
        f"{P}/portfolios/{pid}/orders/preview",
        json={"symbol": "KO", "side": "buy", "quantity": "1", "client_order_id": "p1"},
    ).json()
    assert preview["decision"]["execution"]["commission"] == "4.50"


def test_zero_fees_are_allowed_and_survive_a_restart(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as c:
        assert (
            c.put(
                f"{P}/fees", headers=H, json={"per_trade": "0", "per_withdrawal": "0"}
            ).status_code
            == 200
        )
    with TestClient(create_app(settings(tmp_path))) as c:
        assert c.get(f"{P}/fees").json()["per_trade"] == "0.00"
        pid = make_portfolio(c, "10000")
        assert buy(c, pid)["decision"]["execution"]["commission"] == "0.00"


def test_bad_fees_are_refused(client: TestClient) -> None:
    for body in ({}, {"per_trade": "-1"}, {"per_withdrawal": "1001"}, {"per_trade": "abc"}):
        assert client.put(f"{P}/fees", headers=H, json=body).status_code == 422, body
    assert client.get(f"{P}/fees").json()["per_trade"] == "1.00"
    assert client.put(f"{P}/fees", json={"per_trade": "2"}).status_code == 403


def test_a_fee_too_big_for_the_cash_rejects_the_order(client: TestClient) -> None:
    pid = make_portfolio(client, "100")
    client.put(f"{P}/fees", headers=H, json={"per_trade": "1000"})
    outcome = buy(client, pid, quantity="1")
    assert outcome["decision"]["status"] == "rejected"


def test_a_withdrawal_costs_its_fee_and_is_recorded_as_a_fee(client: TestClient) -> None:
    pid = make_portfolio(client, "1000")
    r = client.post(f"{P}/portfolios/{pid}/withdraw", headers=H, json={"amount": "100"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cash_balance"] == "899.00"  # 1000 - 100 withdrawn - 1 fee
    assert body["fees_paid"] == "1.00"
    # The fee is a cost, not money taken out: contributions only fall by the amount withdrawn.
    assert body["net_contributions"] == "900.00"
    kinds = [e["kind"] for e in client.get(f"{P}/portfolios/{pid}/history").json()["entries"]]
    assert kinds.count("withdrawal") == 1 and kinds.count("fee") == 1
    report = client.get("/api/v1/system/reconcile").json()
    assert not [i for i in report["issues"] if i["severity"] == "error"], report


def test_the_withdrawal_fee_must_be_covered_by_the_cash(client: TestClient) -> None:
    pid = make_portfolio(client, "100")
    # The amount alone fits, but the amount plus the 1.00 fee does not.
    refused = client.post(f"{P}/portfolios/{pid}/withdraw", headers=H, json={"amount": "99.50"})
    assert refused.status_code in {409, 422}
    assert "withdrawal fee" in refused.text
    assert client.get(f"{P}/portfolios/{pid}").json()["cash_balance"] == "100.00"


def test_no_withdrawal_fee_means_no_fee_entry(client: TestClient) -> None:
    pid = make_portfolio(client, "1000")
    client.put(f"{P}/fees", headers=H, json={"per_withdrawal": "0"})
    r = client.post(f"{P}/portfolios/{pid}/withdraw", headers=H, json={"amount": "100"}).json()
    assert r["cash_balance"] == "900.00" and Decimal(r["fees_paid"]) == 0
    kinds = [e["kind"] for e in client.get(f"{P}/portfolios/{pid}/history").json()["entries"]]
    assert "fee" not in kinds


def test_fee_changes_are_audited(client: TestClient) -> None:
    client.put(f"{P}/fees", headers=H, json={"per_trade": "2.25"})
    audit = client.get("/api/v1/system/audit").json()
    changed = [a for a in audit["entries"] if a["action"] == "paper.fees.changed"]
    assert changed and changed[0]["detail"]["per_trade"] == "2.25"
    assert changed[0]["detail"]["previous_per_trade"] == "1.00"
