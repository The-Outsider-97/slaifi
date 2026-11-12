"""Plain-language messages for rejected request bodies.

FastAPI's default 422 carries pydantic's terse text ("Input should be a valid decimal") with a
location list the UI cannot show. These helpers turn each failure into a sentence that names the
field, says what was wrong, and gives an example — so a person who typed "USD" into a money box
is told that money boxes take digits, not which pydantic validator tripped.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

# Labels shown to people. Anything not listed falls back to the field name in sentence case.
FIELD_LABELS: Mapping[str, str] = {
    "name": "Name",
    "currency": "Currency",
    "basis": "Goal type",
    "target_amount": "Target amount",
    "target_value": "Balance to reach",
    "period": "Period",
    "target_annual_rate": "Target yearly return",
    "horizon_years": "Time horizon (years)",
    "starting_capital": "Starting capital",
    "monthly_contribution": "Monthly contribution",
    "monthly_withdrawal": "Monthly withdrawal",
    "risk_tolerance": "Risk tolerance",
    "max_acceptable_drawdown_rate": "Largest acceptable drop",
    "portfolio_id": "Portfolio",
    "assumed_annual_return_rate": "Assumed yearly return",
    "amount": "Amount",
    "quantity": "Quantity",
    "notional": "Order value",
    "symbol": "Symbol",
    "side": "Buy or sell",
    "text": "Message",
    "strategy_id": "Strategy",
    "preset_id": "Starting template",
    "symbols": "Symbols",
}

_NUMBER_ERRORS = {
    "decimal_parsing",
    "decimal_type",
    "float_parsing",
    "float_type",
    "int_parsing",
    "int_type",
    "int_from_float",
}


def label_for(field: str) -> str:
    if field in FIELD_LABELS:
        return FIELD_LABELS[field]
    text = field.replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else "This field"


def _field_name(loc: Sequence[Any]) -> str:
    parts = [str(p) for p in loc if p not in ("body", "query", "path", "header")]
    return parts[-1] if parts else ""


def _shown(value: Any) -> str:
    text = str(value).strip()
    return f"“{text[:40]}”" if text else "nothing"


def _bound(ctx: Mapping[str, Any], key: str) -> str:
    """A limit as people write it: 0.0 → 0, 100.0 → 100, -1 stays -1."""
    raw = ctx.get(key, "")
    try:
        value = Decimal(str(raw))
    except InvalidOperation:
        return str(raw)
    text = format(value.normalize(), "f")
    return text if text not in {"-0", ""} else "0"


def explain_error(error: Mapping[str, Any]) -> dict[str, str]:
    """One pydantic error → ``{field, label, message}`` with a human sentence."""
    kind = str(error.get("type", ""))
    ctx: Mapping[str, Any] = error.get("ctx") or {}
    field = _field_name(error.get("loc") or ())
    label = label_for(field) if field else "Request"
    given = error.get("input")

    if kind in _NUMBER_ERRORS:
        message = (
            f"must be a plain number such as 5000 or 5000.50 — you entered {_shown(given)}. "
            "Type digits only (no currency words like USD; the currency is chosen separately)."
        )
    elif kind in {"greater_than", "decimal_greater_than"}:
        message = f"must be greater than {_bound(ctx, 'gt')}."
    elif kind in {"greater_than_equal"}:
        bound = _bound(ctx, "ge")
        message = f"cannot be less than {bound}." if bound != "0" else "cannot be negative."
    elif kind == "less_than":
        message = f"must be less than {_bound(ctx, 'lt')}."
    elif kind == "less_than_equal":
        message = f"cannot be more than {_bound(ctx, 'le')}."
    elif kind == "decimal_max_digits":
        message = "has too many digits."
    elif kind == "decimal_max_places":
        places = ctx.get("decimal_places", 2)
        message = f"can have at most {places} decimal places."
    elif kind == "decimal_whole_digits":
        message = "is too large."
    elif kind == "missing":
        message = "is required."
    elif kind == "string_too_short":
        message = (
            "cannot be empty."
            if int(ctx.get("min_length", 1)) <= 1
            else f"needs at least {ctx.get('min_length')} characters."
        )
    elif kind == "string_too_long":
        message = f"is too long (at most {ctx.get('max_length')} characters)."
    elif kind == "too_short":
        message = f"needs at least {ctx.get('min_length')} item(s)."
    elif kind == "too_long":
        message = f"allows at most {ctx.get('max_length')} item(s)."
    elif kind == "string_pattern_mismatch":
        message = "is not in an accepted format."
    elif kind in {"enum", "literal_error"}:
        expected = str(ctx.get("expected", "")).replace("'", "")
        message = f"must be one of: {expected}." if expected else "is not an allowed choice."
    elif kind == "extra_forbidden":
        message = "is not a setting this form understands."
    elif kind in {"bool_parsing", "bool_type"}:
        message = "must be yes or no."
    elif kind in {"string_type"}:
        message = "must be text."
    else:
        raw = str(error.get("msg", "is not valid."))
        message = raw[:1].lower() + raw[1:]
    return {"field": field, "label": label, "message": message}


def explain_errors(errors: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The 422 response body for a list of pydantic errors."""
    if len(errors) == 1 and errors[0].get("type") == "json_invalid":
        sentence = "The request could not be read. Reload the page and try again."
        return {"error": "validation_error", "detail": sentence, "fields": []}
    items = [explain_error(e) for e in errors]
    sentences = [
        f"{item['label']} {item['message']}" if item["field"] else f"The request {item['message']}"
        for item in items
    ]
    return {
        "error": "validation_error",
        "detail": " ".join(sentences),
        "fields": items,
    }
