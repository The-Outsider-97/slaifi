from pathlib import Path

import pytest
from pydantic import ValidationError

from slaifi.core.config import Settings


def test_settings_do_not_auto_load_dotenv_from_cwd(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / ".env").write_text(
        "SLAIFI_LOG_LEVEL=ERROR\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    assert settings.log_level == "INFO"


def test_settings_can_explicitly_load_dotenv(tmp_path: Path) -> None:
    env_file = tmp_path / "explicit.env"
    env_file.write_text(
        "SLAIFI_LOG_LEVEL=ERROR\n",
        encoding="utf-8",
    )
    settings = Settings(_env_file=env_file)
    assert settings.log_level == "ERROR"


def test_no_mock_or_illustrative_setting_exists() -> None:
    fields = set(Settings.model_fields)
    assert not {f for f in fields if "mock" in f or "illustrative" in f}
    assert "market_provider" not in fields


def test_unknown_provider_in_order_is_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown provider"):
        Settings(environment="test", market_provider_order="twelvedata,mock")


def test_provider_order_is_normalised_and_deduplicated() -> None:
    s = Settings(environment="test", market_provider_order=" Tiingo , twelvedata,tiingo ")
    assert s.provider_order == ("tiingo", "twelvedata")


def test_each_provider_has_its_own_key_and_blank_means_not_configured() -> None:
    s = Settings(
        environment="test",
        tiingo_api_key="tk",
        fmp_api_key="  ",
        finnhub_api_key="fk",
    )
    assert s.provider_key("tiingo") == "tk"
    assert s.provider_key("finnhub") == "fk"
    assert s.provider_key("fmp") is None
    assert s.provider_key("alphavantage") is None
    assert "tk" not in repr(s) and "fk" not in repr(s)


def test_legacy_market_api_key_is_the_twelve_data_key() -> None:
    s = Settings(environment="test", market_api_key="legacy")
    assert s.provider_key("twelvedata") == "legacy"
    assert s.provider_key("tiingo") is None
    specific = Settings(environment="test", market_api_key="legacy", twelvedata_api_key="new")
    assert specific.provider_key("twelvedata") == "new"


def test_provider_keys_can_come_from_the_environment(monkeypatch) -> None:
    monkeypatch.setenv("SLAIFI_TIINGO_API_KEY", "abc")
    monkeypatch.setenv("SLAIFI_FMP_BASE_URL", "http://127.0.0.1:9/")
    s = Settings()
    assert s.provider_key("tiingo") == "abc"
    assert s.provider_base_url("fmp") == "http://127.0.0.1:9/"
    assert s.provider_base_url("tiingo") is None


def test_the_app_starts_with_no_keys_configured() -> None:
    assert Settings(environment="production").provider_key("twelvedata") is None


def test_required_slai_cannot_be_disabled() -> None:
    with pytest.raises(ValidationError, match="required and disabled"):
        Settings(environment="test", slai_enabled=False, slai_required=True)


def test_bounded_cache_configuration_is_exposed() -> None:
    settings = Settings(
        environment="test",
        market_quote_cache_ttl_seconds=3.0,
        market_history_cache_ttl_seconds=45.0,
    )
    assert settings.market_quote_cache_ttl_seconds == 3.0
    assert settings.market_history_cache_ttl_seconds == 45.0


def test_request_limits_can_be_overridden_per_provider() -> None:
    s = Settings(environment="test", market_limits={"twelvedata": {"per_minute": 55}})
    assert s.market_limits["twelvedata"]["per_minute"] == 55


@pytest.mark.parametrize(
    "limits",
    [
        {"nosuch": {"per_minute": 5}},
        {"tiingo": {"per_week": 5}},
        {"tiingo": {"per_minute": 0}},
    ],
)
def test_invalid_request_limits_are_rejected(limits: dict) -> None:
    with pytest.raises(ValidationError):
        Settings(environment="test", market_limits=limits)


def test_limits_reach_the_adapters_through_the_factory() -> None:
    from slaifi.infrastructure.market_data import build_gateway

    s = Settings(
        environment="test",
        twelvedata_api_key="a",
        tiingo_api_key="b",
        market_limits={"twelvedata": {"per_minute": 55, "per_day": 9000}},
    )
    gateway = build_gateway(s, cache=None)
    providers = {p.name: p for p in gateway._providers}
    assert providers["twelvedata"].policy.per_minute == 55
    assert providers["twelvedata"].policy.per_day == 9000
    assert providers["tiingo"].policy.per_hour == 50  # untouched free-tier default
    assert "SLAIFI_MARKET_LIMITS" in providers["twelvedata"].policy.note
