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
    market_overview_symbols: tuple[str, ...] = ("SPY", "QQQ", "DIA")

    # SLAI is optional for standalone SLAIFI operation but fully wired when present.
    slai_enabled: bool = True
    slai_required: bool = False
    slai_reasoning_agent: str = "reasoning"
    slai_reasoning_type: str | None = None
    slai_memory_ttl_seconds: int = Field(default=900, ge=1, le=86_400)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached process settings snapshot."""

    return Settings()
