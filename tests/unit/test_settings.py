from pathlib import Path
from slaifi.core.config import Settings

def test_settings_do_not_auto_load_dotenv_from_cwd(tmp_path:Path,monkeypatch)->None:
    (tmp_path/".env").write_text("SLAIFI_LOG_LEVEL=ERROR\n",encoding="utf-8"); monkeypatch.chdir(tmp_path)
    assert Settings().log_level == "INFO"

def test_settings_can_explicitly_load_dotenv(tmp_path:Path)->None:
    path=tmp_path/"explicit.env"; path.write_text("SLAIFI_LOG_LEVEL=ERROR\n",encoding="utf-8")
    assert Settings(_env_file=path).log_level == "ERROR"
