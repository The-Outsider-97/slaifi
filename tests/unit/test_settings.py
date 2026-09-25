from pathlib import Path

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
