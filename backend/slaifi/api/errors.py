"""Stable HTTP mappings for expected SLAIFI failures."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from logs.logger import get_logger

from slaifi.api.security import ClientHeaderRequired
from slaifi.application.contracts import ReasoningUnavailableError
from slaifi.core.utils.errors import (
    CalculationError,
    ConflictError,
    MarketDataError,
    MarketDataRateLimitedError,
    MarketDataUnavailableError,
    NotFoundError,
    SlaifiError,
    SymbolNotFoundError,
    ValidationError,
)

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

    @app.exception_handler(ClientHeaderRequired)
    async def client_header_required(_: Request, exc: ClientHeaderRequired) -> JSONResponse:
        return JSONResponse(
            status_code=403, content={"error": "client_header_required", "detail": str(exc)}
        )

    @app.exception_handler(NotFoundError)
    async def not_found(_: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"error": "not_found", "detail": str(exc)})

    # SymbolNotFoundError is both a MarketDataError and a NotFoundError; Starlette resolves
    # handlers by walking the MRO, so it is registered explicitly to stay a 404.
    @app.exception_handler(SymbolNotFoundError)
    async def symbol_not_found(_: Request, exc: SymbolNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404, content={"error": "symbol_not_found", "detail": str(exc)}
        )

    @app.exception_handler(ConflictError)
    async def conflict(_: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"error": "conflict", "detail": str(exc)})

    @app.exception_handler(MarketDataRateLimitedError)
    async def rate_limited(_: Request, exc: MarketDataRateLimitedError) -> JSONResponse:
        headers = {}
        if exc.retry_after_seconds is not None:
            headers["Retry-After"] = str(max(1, int(exc.retry_after_seconds)))
        return JSONResponse(
            status_code=429,
            headers=headers,
            content={"error": "market_data_rate_limited", "detail": str(exc), "retryable": True},
        )

    @app.exception_handler(MarketDataUnavailableError)
    async def market_unavailable(_: Request, exc: MarketDataUnavailableError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"error": "market_data_unavailable", "detail": str(exc), "retryable": True},
        )

    @app.exception_handler(MarketDataError)
    async def market_error(_: Request, exc: MarketDataError) -> JSONResponse:
        return JSONResponse(
            status_code=502, content={"error": "market_data_error", "detail": str(exc)}
        )

    @app.exception_handler(SlaifiError)
    async def slaifi_error(_: Request, exc: SlaifiError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"error": "slaifi_error", "detail": str(exc)},
        )

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception) -> JSONResponse:
        # Details stay in the log; the response never leaks internals, paths or credentials.
        logger.exception("Unhandled SLAIFI API error: %s", type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "detail": "An unexpected error occurred. See the server log.",
            },
        )
