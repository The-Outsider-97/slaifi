"""End-to-end workflow through the HTTP API on the mock provider (illustrative data).

Mirrors the twelve-step acceptance workflow: market data → strategy → portfolio → recommendation
→ simulated trading → advisor → goals → guidance → restart persistence → reset.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from slaifi.core.config import Settings
from slaifi.main import create_app

H = {"X-SLAIFI-Client": "test"}


def _client(data_dir: Path, **overrides: object) -> TestClient:
    settings = Settings(environment="test", data_dir=data_dir, slai_enabled=False, **overrides)  # type: ignore[arg-type]
    return TestClient(create_app(settings), raise_server_exceptions=False)


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture()
def client(data_dir: Path) -> Iterator[TestClient]:
    with _client(data_dir) as c:
        yield c


def test_twelve_step_workflow_with_restart(data_dir: Path) -> None:
    with _client(data_dir) as c:
        # 1. system is up, ledger healthy, real money unavailable
        status = c.get("/api/v1/system/status").json()
        assert status["storage_status"] == "ok"
        assert status["audit_chain_intact"] is True
        assert status["real_money_trading"] == "unavailable"
        assert status["data_mode"] == "mock"

        # 2. search and quote are labelled mock/illustrative, never live
        found = c.get("/api/v1/market/search", params={"q": "apple"}).json()
        assert found["results"][0]["asset"]["symbol"] == "AAPL"
        assert found["provenance"]["mode"] == "mock"
        quote = c.get("/api/v1/market/quote/AAPL").json()
        assert quote["provenance"]["mode"] == "mock"
        assert quote["provenance"]["illustrative"] is True

        # 3. series with indicator overlays and quality metadata
        series = c.get(
            "/api/v1/market/series/AAPL", params={"range": "6M", "overlays": "sma20,rsi14"}
        ).json()
        assert len(series["bars"]) > 50
        assert set(series["overlays"]) == {"sma20", "rsi14"}
        assert series["quality"]["count"] == len(series["bars"])
        stats = c.get("/api/v1/market/stats/AAPL").json()
        assert stats["observation_count"] > 100
        assert stats["provenance"]["illustrative"] is True
        compare = c.get("/api/v1/market/compare", params={"symbols": "AAPL,MSFT"}).json()
        assert len(compare["series"]) == 2

        # 4. strategies: presets initialise, values stay editable
        listing = c.get("/api/v1/strategies").json()
        assert listing["presets"]
        created = c.post(
            "/api/v1/strategies",
            headers=H,
            json={
                "name": "Mine",
                "preset_id": listing["presets"][0]["preset"],
                "fields": {"max_position_weight": 0.3},
            },
        )
        assert created.status_code == 201
        assert created.json()["max_position_weight"] == pytest.approx(0.3)

        # 5. portfolio
        pf = c.post(
            "/api/v1/paper/portfolios",
            headers=H,
            json={"name": "Practice", "starting_capital": "10000.00"},
        )
        assert pf.status_code == 201
        pid = pf.json()["portfolio"]["portfolio_id"]
        assert pf.json()["cash_balance"] == "10000.00"
        assert pf.json()["simulated"] is True

        # 6. recommendation on illustrative data must refuse to recommend
        rec = c.get("/api/v1/recommendations/AAPL", params={"portfolio_id": pid}).json()
        assert rec["report"]["status"] == "insufficient_evidence"
        assert rec["report"]["action"] is None
        assert rec["report"]["prediction"] is None
        assert rec["provenance"]["illustrative"] is True

        # 7. order preview does not change the ledger; real order does
        # The default strategy's hard limits beat the request: AAPL is too volatile and too large.
        blocked = c.post(
            f"/api/v1/paper/portfolios/{pid}/orders",
            headers=H,
            json={"symbol": "AAPL", "side": "buy", "quantity": "10"},
        ).json()
        assert blocked["decision"]["status"] == "rejected"
        assert {r["code"] for r in blocked["decision"]["rejections"]} == {"strategy_constraint"}
        order = {"symbol": "JNJ", "side": "buy", "quantity": "5", "client_order_id": "wf-1"}
        preview = c.post(f"/api/v1/paper/portfolios/{pid}/orders/preview", json=order).json()
        assert preview["dry_run"] is True
        assert c.get(f"/api/v1/paper/portfolios/{pid}").json()["positions"] == []
        placed = c.post(f"/api/v1/paper/portfolios/{pid}/orders", headers=H, json=order).json()
        assert placed["decision"]["status"] == "filled"
        assert placed["decision"]["execution"]["illustrative"] is True
        again = c.post(f"/api/v1/paper/portfolios/{pid}/orders", headers=H, json=order).json()
        assert again["duplicate"] is True
        view = c.get(f"/api/v1/paper/portfolios/{pid}").json()
        assert len(view["positions"]) == 1
        assert view["positions"][0]["asset"]["symbol"] == "JNJ"
        assert view["simulated"] is True

        # 8. advisor: preview only, then explicit confirmation executes a simulated order
        adv = c.post(
            "/api/v1/advisor/interpret",
            json={"text": "buy $500 of KO", "portfolio_id": pid, "explain": False},
        ).json()
        assert adv["requires_confirmation"] is True
        assert adv["orders"][0]["preview"]["decision"]["status"] == "filled"
        assert (
            len(c.get(f"/api/v1/paper/portfolios/{pid}").json()["positions"]) == 1
        )  # nothing happened yet
        conf = c.post(
            f"/api/v1/advisor/proposals/{adv['proposal']['proposal_id']}/confirm",
            headers=H,
            json={},
        )
        assert conf.status_code == 200, conf.text
        assert len(c.get(f"/api/v1/paper/portfolios/{pid}").json()["positions"]) == 2

        # 9. goals
        goal = c.post(
            "/api/v1/goal-tracker",
            headers=H,
            json={
                "name": "Monthly",
                "target_amount": "200",
                "period": "monthly",
                "basis": "realized_profit",
            },
        )
        assert goal.status_code == 201, goal.text
        report = c.post(
            f"/api/v1/goal-tracker/{goal.json()['goal_id']}/analyze", json={"portfolio_id": pid}
        ).json()
        assert report["required_annual_return_rate"] is not None
        assert "guarantee" in report["disclaimer"].lower()

        # 10. guidance
        guidance = c.get(f"/api/v1/paper/portfolios/{pid}/guidance").json()
        assert guidance["metrics"] is not None
        assert guidance["disclaimer"].startswith("Decision support")

        # 11. reconciliation and audit are consistent
        rec_report = c.get(f"/api/v1/paper/portfolios/{pid}/reconcile").json()
        assert rec_report["consistent"] is True
        assert rec_report["trade_count"] == 2
        cash_before = c.get(f"/api/v1/paper/portfolios/{pid}").json()["cash_balance"]

    # restart with the same data folder: everything is recovered from the ledger
    with _client(data_dir) as c2:
        assert c2.get("/api/v1/system/status").json()["storage_status"] == "ok"
        view = c2.get(f"/api/v1/paper/portfolios/{pid}").json()
        assert view["cash_balance"] == cash_before
        assert len(view["positions"]) == 2
        assert len(c2.get("/api/v1/goal-tracker").json()["goals"]) == 1
        assert c2.get(f"/api/v1/paper/portfolios/{pid}/reconcile").json()["consistent"] is True

        # 12. reset requires explicit confirmation, then restores starting capital
        refused = c2.post(f"/api/v1/paper/portfolios/{pid}/reset", headers=H, json={})
        assert refused.status_code == 422
        done = c2.post(f"/api/v1/paper/portfolios/{pid}/reset", headers=H, json={"confirm": True})
        assert done.status_code == 200
        assert done.json()["positions"] == []
        assert done.json()["cash_balance"] == "10000.00"
