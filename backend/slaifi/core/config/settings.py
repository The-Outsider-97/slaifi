"""Central, location-independent SLAIFI runtime settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
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

    # Market data. Mock mode is explicit and forbidden in production.
    market_provider: Literal["mock", "twelvedata"] = "mock"
    market_api_key: str | None = None
    market_http_timeout_seconds: float = Field(default=10.0, gt=0.0, le=60.0)
    market_quote_cache_ttl_seconds: float = Field(default=5.0, ge=0.0, le=60.0)
    market_history_cache_ttl_seconds: float = Field(default=60.0, ge=0.0, le=900.0)
    market_overview_symbols: tuple[str, ...] = ("SPY", "QQQ", "DIA", "VIX")

    # Optional JSON ledger containing actual portfolio state.
    portfolio_file: Path | None = None

    # SLAI integration. Deterministic finance continues when SLAI is optional/unavailable.
    slai_enabled: bool = True
    slai_required: bool = False
    slai_reasoning_agent: str = "reasoning"
    slai_reasoning_type: str | None = None
    slai_quality_enabled: bool = True
    slai_quality_agent: str = "quality"
    slai_quality_refinement_enabled: bool = True
    slai_safety_enabled: bool = True
    slai_safety_agent: str = "safety"
    slai_memory_ttl_seconds: int = Field(default=900, ge=1, le=86_400)

    @model_validator(mode="after")
    def validate_runtime_contract(self) -> "Settings":
        if self.environment == "production" and self.market_provider == "mock":
            raise ValueError("production cannot use the mock market provider")
        if self.market_provider == "twelvedata" and not (self.market_api_key or "").strip():
            raise ValueError(
                "SLAIFI_MARKET_API_KEY is required when SLAIFI_MARKET_PROVIDER=twelvedata"
            )
        if self.slai_required and not self.slai_enabled:
            raise ValueError("SLAI cannot be both required and disabled")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached process settings snapshot."""

    return Settings()
