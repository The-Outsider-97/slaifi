import importlib
from pathlib import Path


def test_root_launcher_imports_independently_of_current_working_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    module = importlib.import_module("run_slaifi")
    assert callable(module.main)


def test_root_launcher_contains_no_path_mutation() -> None:
    source = (Path(__file__).parents[2] / "run_slaifi.py").read_text(encoding="utf-8")
    assert "sys.path" not in source
    assert "os.getcwd" not in source
    assert "Path.cwd" not in source
