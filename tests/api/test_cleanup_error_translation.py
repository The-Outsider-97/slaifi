from fastapi import FastAPI
from fastapi.testclient import TestClient

from slaifi.api.errors import install_exception_handlers
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
