"""Cleanup-specific architectural regression rules."""

from pathlib import Path

ROOT = Path(__file__).parents[2]
PACKAGE_ROOT = ROOT / "backend" / "slaifi"


def test_duplicate_local_logging_implementation_is_absent() -> None:
    assert not (PACKAGE_ROOT / "core" / "logging").exists()
    for path in PACKAGE_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "slaifi.core.logging" not in text
        assert "logging.basicConfig" not in text
        # The provider base may only *silence* third-party HTTP request logging, which would
        # otherwise print query-string API keys. It does not implement any logging of its own.
        if path != PACKAGE_ROOT / "infrastructure" / "market_data" / "base.py":
            assert "logging.getLogger" not in text


def test_removed_error_and_engine_helper_implementations_stay_removed() -> None:
    assert not (PACKAGE_ROOT / "core" / "exceptions" / "base.py").exists()
    assert not (PACKAGE_ROOT / "engines" / "_validation.py").exists()


def test_operational_layers_use_canonical_slai_logger() -> None:
    expected = (
        PACKAGE_ROOT / "main.py",
        PACKAGE_ROOT / "application" / "market" / "get_overview.py",
        PACKAGE_ROOT / "api" / "errors.py",
        PACKAGE_ROOT / "integrations" / "slai" / "reasoner.py",
    )
    for path in expected:
        text = path.read_text(encoding="utf-8")
        assert "from logs.logger import get_logger" in text


def test_no_mock_or_illustrative_data_path_ships_in_the_package() -> None:
    assert not list(PACKAGE_ROOT.rglob("*mock*.py"))
    offenders: list[str] = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for token in ("illustrative", "mockmarket", "mock_provider", 'data_mode == "mock"'):
            if token in text:
                offenders.append(f"{path.relative_to(ROOT)} mentions {token}")
    assert not offenders, "\n".join(offenders)


def test_backend_and_launcher_contain_no_path_hacks() -> None:
    forbidden = ("os.getcwd(", "Path.cwd(", "sys.path.append(", "sys.path.insert(")
    paths = [*PACKAGE_ROOT.rglob("*.py"), ROOT / "__main__.py"]
    violations: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                violations.append(f"{path.relative_to(ROOT)} contains {token}")
    assert not violations, "\n".join(violations)
