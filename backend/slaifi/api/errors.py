"""Stable HTTP mappings for expected SLAIFI failures."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from logs.logger import get_logger

from slaifi.application.contracts import ReasoningUnavailableError
from slaifi.core.utils.errors import CalculationError, SlaifiError, ValidationError

logger = get_logger("SLAIFI API")


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ReasoningUnavailableError)
    async def reasoning_unavailable(
        _: Request,
        exc: ReasoningUnavailableError,
    ) -> JSONResponse:
        logger.warning("Required SLAI reasoning is unavailable: %s", exc)
        return JSONResponse(
            status_code=503,
            content={"error": "reasoning_unavailable", "detail": str(exc)},
        )

    @app.exception_handler(ValidationError)
    async def validation_error(_: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": "validation_error", "detail": str(exc)},
        )

    @app.exception_handler(CalculationError)
    async def calculation_error(
        _: Request,
        exc: CalculationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": "financial_calculation_error", "detail": str(exc)},
        )

    @app.exception_handler(SlaifiError)
    async def slaifi_error(_: Request, exc: SlaifiError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"error": "slaifi_error", "detail": str(exc)},
        )
