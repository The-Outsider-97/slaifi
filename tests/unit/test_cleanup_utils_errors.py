from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

import pytest

from slaifi.core.utils import SlaifiError, ValidationError, is_aware_datetime, to_json_safe
from slaifi.domain.utils import DomainError, DomainValidationError, normalize_identifier
from slaifi.engines.utils import EngineError, FinancialCalculationError, finite_series


class ExampleStatus(StrEnum):
    OK = "ok"


def test_core_error_preserves_structured_context() -> None:
    cause = RuntimeError("network")
    exc = SlaifiError(
        "operation failed",
        component="test",
        operation="load",
        cause=cause,
        context={"asset": "ABC"},
        retryable=True,
    )
    assert str(exc) == "operation failed"
    assert exc.as_dict() == {
        "error_type": "SlaifiError",
        "message": "operation failed",
        "component": "test",
        "operation": "load",
        "context": {"asset": "ABC"},
        "retryable": True,
        "cause_type": "RuntimeError",
    }


def test_domain_and_engine_errors_inherit_from_core_categories() -> None:
    assert issubclass(DomainValidationError, DomainError)
    assert issubclass(DomainValidationError, ValidationError)
    assert issubclass(FinancialCalculationError, EngineError)
    assert issubclass(FinancialCalculationError, ArithmeticError)


def test_core_json_safe_and_datetime_helpers() -> None:
    aware = datetime(2026, 9, 25, tzinfo=UTC)
    assert is_aware_datetime(aware)
    assert not is_aware_datetime(datetime(2026, 9, 25))
    payload = to_json_safe(
        {"time": aware, "money": Decimal("1.25"), "status": ExampleStatus.OK}
    )
    assert payload == {
        "time": str(aware),
        "money": "1.25",
        "status": "ok",
    }


def test_domain_identifier_and_engine_series_helpers() -> None:
    assert normalize_identifier(" xnas ", name="exchange", uppercase=True) == "XNAS"
    with pytest.raises(DomainValidationError):
        normalize_identifier("   ", name="exchange")
    assert finite_series([1, 2.5], minimum=2) == (1.0, 2.5)
    with pytest.raises(ValidationError):
        finite_series([1.0, float("nan")])
