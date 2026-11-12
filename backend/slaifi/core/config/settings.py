"""Central, location-independent SLAIFI runtime settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

KNOWN_PROVIDERS = ("twelvedata", "tiingo", "fmp", "finnhub", "alphavantage")


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
    # Built web UI served by the API (default: <slaifi root>/frontend/dist when it exists).
    frontend_dist_dir: Path | None = None

    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )
    api_max_market_bars: int = Field(default=5000, ge=2, le=100_000)
    api_max_portfolio_trades: int = Field(default=10_000, ge=1, le=1_000_000)
    # Mutating requests must carry the SLAIFI client marker header (see api.security).
    api_require_client_header: bool = True

    # Market data. SLAIFI asks the providers below in this order and falls back to its saved
    # last-known observations; it never generates prices. Each provider needs its own free key.
    market_provider_order: str = "twelvedata,tiingo,fmp,finnhub,alphavantage"
    twelvedata_api_key: SecretStr | None = None
    tiingo_api_key: SecretStr | None = None
    fmp_api_key: SecretStr | None = None
    finnhub_api_key: SecretStr | None = None
    alphavantage_api_key: SecretStr | None = None
    # Legacy name for the Twelve Data key (still honoured when the specific one is not set).
    market_api_key: SecretStr | None = None
    # Optional endpoint overrides (an internal proxy, or a local stand-in server for tests).
    twelvedata_base_url: str | None = None
    tiingo_base_url: str | None = None
    fmp_base_url: str | None = None
    finnhub_base_url: str | None = None
    alphavantage_base_url: str | None = None
    # Raise (or lower) a provider's self-imposed request budget, for example on a paid plan:
    # SLAIFI_MARKET_LIMITS='{"twelvedata": {"per_minute": 55, "per_day": 50000}}'
    market_limits: dict[str, dict[str, int]] = Field(default_factory=dict)
    market_http_timeout_seconds: float = Field(default=10.0, gt=0.0, le=60.0)
    market_quote_cache_ttl_seconds: float = Field(default=60.0, ge=0.0, le=300.0)
    market_history_cache_ttl_seconds: float = Field(default=300.0, ge=0.0, le=3600.0)
    market_overview_symbols: tuple[str, ...] = ("SPY", "QQQ", "DIA", "VIX")
    # Known provider delay in minutes for Twelve Data (for example 15 on a delayed plan). None
    # means unknown; SLAIFI then reports quote age but never claims the feed is real time.
    market_data_delay_minutes: int | None = Field(default=None, ge=0, le=1440)

    # Paper trading. Real-money trading does not exist in SLAIFI and cannot be enabled.
    paper_allow_closed_market_execution: bool = False
    paper_max_quote_age_seconds: int = Field(default=900, ge=1, le=86_400)

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
    slai_memory_ttl_seconds: int = Field(default=900, ge=1, le=86_400)

    @model_validator(mode="after")
    def validate_runtime_contract(self) -> "Settings":
        unknown = [n for n in self.provider_order if n not in KNOWN_PROVIDERS]
        if unknown:
            raise ValueError(
                f"SLAIFI_MARKET_PROVIDER_ORDER names unknown provider(s) {', '.join(unknown)}; "
                f"choose from {', '.join(KNOWN_PROVIDERS)}"
            )
        for name, windows in self.market_limits.items():
            if name not in KNOWN_PROVIDERS:
                raise ValueError(f"SLAIFI_MARKET_LIMITS names unknown provider {name!r}")
            for window, value in windows.items():
                if window not in ("per_minute", "per_hour", "per_day") or value < 1:
                    raise ValueError(
                        f"SLAIFI_MARKET_LIMITS[{name!r}] must use per_minute/per_hour/per_day "
                        "with whole numbers of at least 1"
                    )
        if self.slai_required and not self.slai_enabled:
            raise ValueError("SLAI cannot be both required and disabled")
        return self

    @property
    def provider_order(self) -> tuple[str, ...]:
        names = [n.strip().lower() for n in self.market_provider_order.split(",") if n.strip()]
        return tuple(dict.fromkeys(names))

    def provider_key(self, name: str) -> str | None:
        """The configured API key for a provider, or ``None`` when it is not configured."""

        secret = getattr(self, f"{name}_api_key", None)
        if secret is None and name == "twelvedata":
            secret = self.market_api_key
        value = secret.get_secret_value().strip() if secret is not None else ""
        return value or None

    def provider_base_url(self, name: str) -> str | None:
        value = getattr(self, f"{name}_base_url", None)
        return str(value).strip() or None if value else None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached process settings snapshot."""

    return Settings()
