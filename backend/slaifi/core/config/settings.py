"""Central, location-independent SLAIFI runtime settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings sourced from environment variables or explicit arguments.

    SLAIFI intentionally does not auto-load ``.env`` from the current working
    directory. A caller that wants dotenv loading must pass ``_env_file``
    explicitly, which keeps package behavior stable when installed under
    ``SLAI/applications/slaifi`` or launched from another working directory.
    """

    model_config = SettingsConfigDict(
        env_prefix="SLAIFI_",
        extra="ignore",
        frozen=True,
    )

    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    data_dir: Path | None = None

    # Retained for compatibility with the architecture-foundation API bootstrap.
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )
    market_overview_symbols: tuple[str, ...] = ("SPY", "QQQ", "DIA")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached process settings snapshot."""

    return Settings()
