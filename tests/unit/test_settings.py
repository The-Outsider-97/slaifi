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


def test_production_rejects_mock_market_provider() -> None:
    with pytest.raises(ValidationError, match="production cannot use the mock market provider"):
        Settings(environment="production", market_provider="mock")


def test_live_market_provider_requires_api_key() -> None:
    with pytest.raises(ValidationError, match="SLAIFI_MARKET_API_KEY"):
        Settings(environment="test", market_provider="twelvedata", market_api_key=" ")


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
