"""Central, location-independent SLAIFI runtime settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings sourced from environment variables or explicit arguments."""

    model_config = SettingsConfigDict(
        env_prefix="SLAIFI_",
        extra="ignore",
        frozen=True,
    )

    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    data_dir: Path | None = None

    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )

    api_max_market_bars: int = Field(default=5000, ge=2, le=100_000)
    api_max_portfolio_trades: int = Field(default=10_000, ge=1, le=1_000_000)

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------
    market_provider: Literal["mock", "twelvedata"] = "mock"
    market_api_key: str | None = None
    market_http_timeout_seconds: float = Field(default=10.0, gt=0.0, le=60.0)

    # Provider-valid symbols can also be overridden from the environment.
    market_overview_symbols: tuple[str, ...] = (
        "SPY",
        "QQQ",
        "DIA",
        "VIX",
    )

    # ------------------------------------------------------------------
    # Portfolio source
    # ------------------------------------------------------------------
    # Optional JSON ledger containing the user's actual portfolio.
    # If unset, GET /api/v1/portfolio/current returns HTTP 204.
    portfolio_file: Path | None = None

    # ------------------------------------------------------------------
    # SLAI
    # ------------------------------------------------------------------
    slai_enabled: bool = True
    slai_required: bool = False
    slai_reasoning_agent: str = "reasoning"
    slai_reasoning_type: str | None = None
    slai_memory_ttl_seconds: int = Field(default=900, ge=1, le=86_400)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached process settings snapshot."""

    return Settings()
