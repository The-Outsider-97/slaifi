from fastapi import FastAPI
from fastapi.testclient import TestClient

from slaifi.api.errors import install_exception_handlers
from slaifi.core.utils.errors import InfrastructureError
from slaifi.engines.utils.errors import FinancialCalculationError


def test_engine_calculation_error_is_translated_only_at_api_boundary() -> None:
    app = FastAPI()
    install_exception_handlers(app)

    @app.get("/fail")
    def fail() -> None:
        raise FinancialCalculationError("undefined reference calculation")

    with TestClient(app) as client:
        response = client.get("/fail")

    assert response.status_code == 422
    assert response.json() == {
        "error": "financial_calculation_error",
        "detail": "undefined reference calculation",
    }


def test_infrastructure_error_is_translated_without_exposing_internal_context() -> None:
    app = FastAPI()
    install_exception_handlers(app)

    @app.get("/provider-fail")
    def provider_fail() -> None:
        raise InfrastructureError(
            "Market-data provider request failed",
            component="market_data",
            operation="quote",
            context={"secret": "must-not-leak"},
            retryable=True,
        )

    with TestClient(app) as client:
        response = client.get("/provider-fail")

    assert response.status_code == 502
    assert response.json() == {
        "error": "infrastructure_error",
        "detail": "Market-data provider request failed",
    }
    assert "secret" not in response.text
