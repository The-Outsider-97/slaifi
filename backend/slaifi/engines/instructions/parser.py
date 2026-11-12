"""Deterministic extraction of goals, preferences and constraints from plain-language text.

This is the *validated structuring layer*. The SLAI reasoning agent may add interpretation and
explanation on top, but nothing becomes a setting unless this parser produced a structured,
bounded value from the user's own words. Every proposed change is checked for contradictions and
is applied only after explicit confirmation (see ``application/advisor``).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation

from slaifi.domain.assets import AssetClass
from slaifi.domain.instructions import (
    Contradiction,
    GoalDraft,
    InstructionIntent,
    OrderDraft,
    ParsedInstruction,
    Persistence,
    ProposedChange,
)
from slaifi.domain.strategies import StrategyProfile

MAX_TEXT_LENGTH = 2000

_TEMPORARY = re.compile(
    r"\b(for now|just (this|today)|temporar(y|ily)|this (week|month|time|session)|today|"
    r"what if|hypothetical(ly)?|suppose|imagine|just checking|for this (trade|analysis))\b",
    re.I,
)
_PERSISTENT = re.compile(
    r"\b(always|from now on|going forward|permanent(ly)?|as a rule|by default|every time|"
    r"set my|change my|update my|make my)\b",
    re.I,
)
_QUESTION = re.compile(
    r"\?\s*$|^\s*(what|how|why|which|should|can|could|is|are|do|does|explain|show)\b", re.I
)

_PERIOD_LABEL = {
    "daily": "day",
    "weekly": "week",
    "monthly": "month",
    "quarterly": "quarter",
    "annual": "year",
}
_PERIOD_WORDS = {
    "day": "daily",
    "daily": "daily",
    "week": "weekly",
    "weekly": "weekly",
    "month": "monthly",
    "monthly": "monthly",
    "quarter": "quarterly",
    "quarterly": "quarterly",
    "year": "annual",
    "yearly": "annual",
    "annum": "annual",
    "annually": "annual",
    "annual": "annual",
}


def _money_pattern(suffix: str) -> str:
    return (
        rf"(?:\$|usd\s*|us\$)\s*(?P<a{suffix}>\d[\d,]*(?:\.\d+)?)\s*(?P<ak{suffix}>k|m)?"
        rf"|(?P<b{suffix}>\d[\d,]*(?:\.\d+)?)\s*(?P<bk{suffix}>k|m)?\s*(?:dollars|usd|bucks)"
    )


_AMOUNT_PER = re.compile(
    rf"(?:{_money_pattern('1')})\s*(?:/|per|a|each|every)\s*(?P<p>day|week|month|quarter|year|annum)\b"
    rf"|(?:{_money_pattern('2')})\s*(?P<pw>daily|weekly|monthly|quarterly|yearly|annually)\b",
    re.I,
)
_RATE_PER_YEAR = re.compile(
    r"(?P<r>\d+(?:\.\d+)?)\s*%\s*(?:/|per|a|each)?\s*(?:year|yr|annum|annually|yearly|annual)\b",
    re.I,
)
_HORIZON = re.compile(
    r"(?P<n>\d+(?:\.\d+)?)\s*[- ]?\s*(?P<u>day|week|month|year)s?\b(?:\s*(?:horizon|time ?frame|plan|growth|outlook))?",
    re.I,
)
_DRAWDOWN = re.compile(
    r"(?:max(?:imum)?\s+drawdown(?:\s+(?:of|at|to))?|drawdown\s+(?:limit|cap)(?:\s+of)?|"
    r"(?:don'?t|do not|never|not)\s+(?:want to\s+)?lose\s+more\s+than|lose\s+no\s+more\s+than|"
    r"limit\s+(?:my\s+)?(?:losses|drawdown)\s+to)\s*(?P<d>\d+(?:\.\d+)?)\s*%",
    re.I,
)
_RESERVE = re.compile(
    r"(?:keep|hold|maintain|leave)\s+(?:at least\s+|about\s+|a\s+)?(?P<c>\d+(?:\.\d+)?)\s*%\s*(?:of\s+\w+\s+)?(?:in\s+)?cash"
    r"|cash\s+(?:reserve|buffer)\s*(?:of|at|to)?\s*(?P<c2>\d+(?:\.\d+)?)\s*%",
    re.I,
)
# "keep any single position under 5%": the noun comes first and the bound last.
_POSITION_AFTER = re.compile(
    r"\b(?:any|each|every|a)\s+(?:single\s+|one\s+)?(?:stock|position|holding|asset|company)\s+"
    r"(?:under|below|at|to|less than|no more than|at most|up to)\s+(?P<w>\d+(?:\.\d+)?)\s*%",
    re.I,
)
_POSITION = re.compile(
    r"(?:no more than|not more than|at most|up to|under|below|less than|max(?:imum)?(?: position(?: size)?)?(?: of)?|cap(?: each)?(?: position)?(?: at)?)"
    r"\s*(?P<w>\d+(?:\.\d+)?)\s*%\s*(?:of (?:my )?(?:portfolio |capital )?)?(?:in|per|for|on)?\s*(?:any |a |one |each |single )*"
    r"(?:stock|position|holding|asset|company|name)?",
    re.I,
)
_VOL_CAP = re.compile(
    r"volatility\s+(?:below|under|of at most|cap(?:ped)? at|limit of)\s*(?P<v>\d+(?:\.\d+)?)\s*%",
    re.I,
)
_CAPITAL = re.compile(
    r"(?:with|starting with|start with|invest(?:ing)?|capital of|have)\s*(?:\$|usd\s*)\s*(?P<a>\d[\d,]*(?:\.\d+)?)\s*(?P<k>k|m)?(?!\s*(?:/|per|a)\s*(?:day|week|month|quarter|year))",
    re.I,
)
_EXCLUDE = re.compile(
    r"(?:avoid|exclude|never buy|don'?t buy|do not buy|no|without|stay away from|skip)\s+(?P<what>[A-Za-z][A-Za-z0-9 ,/&.\-]{0,80})",
    re.I,
)
_TICKER = re.compile(r"\b[A-Z]{1,5}(?:\.[A-Z])?\b")
_NOT_TICKERS = frozenset(
    {
        "A",
        "I",
        "AI",
        "ETF",
        "ETFS",
        "USD",
        "EUR",
        "GBP",
        "US",
        "UK",
        "EU",
        "OK",
        "NO",
        "IT",
        "PM",
        "AM",
        "DCA",
        "BUY",
        "SELL",
        "HOLD",
        "WATCH",
        "AVOID",
        "REDUCE",
        "ALL",
        "AND",
        "THE",
        "FOR",
        "NOT",
        "TO",
        "OR",
        "IN",
        "ON",
        "AT",
        "MY",
        "ME",
        "BE",
        "IS",
        "AS",
        "OF",
        "IF",
        "SO",
        "UP",
        "GDP",
        "CEO",
        "IPO",
        "ROI",
        "SLAI",
        "SLAIFI",
        "YTD",
        "FX",
        "CPI",
        "REIT",
        "REITS",
        "AVG",
        "MAX",
        "MIN",
        "PER",
        "DAY",
        "NOW",
    }
)
_ASSET_WORDS: dict[str, AssetClass] = {
    "crypto": AssetClass.CRYPTO,
    "cryptocurrency": AssetClass.CRYPTO,
    "cryptocurrencies": AssetClass.CRYPTO,
    "bitcoin": AssetClass.CRYPTO,
    "forex": AssetClass.FOREX,
    "currencies": AssetClass.FOREX,
    "bonds": AssetClass.BOND,
    "bond": AssetClass.BOND,
    "commodities": AssetClass.COMMODITY,
    "commodity": AssetClass.COMMODITY,
    "etfs": AssetClass.ETF,
    "etf": AssetClass.ETF,
    "index funds": AssetClass.INDEX,
    "index fund": AssetClass.INDEX,
    "indices": AssetClass.INDEX,
    "stocks": AssetClass.EQUITY,
    "equities": AssetClass.EQUITY,
}
_ORDER = re.compile(
    r"\b(?P<side>buy|sell|purchase|short|cover)\s+(?:(?P<qty>\d+(?:\.\d+)?)\s*(?:shares?|units?)?\s*(?:of\s+)?|"
    r"(?:\$|usd\s*)(?P<amt>\d[\d,]*(?:\.\d+)?)(?P<k>k)?\s*(?:worth\s+)?(?:of\s+)?|(?P<all>all|everything)\s+(?:of\s+)?(?:my\s+)?)"
    r"(?P<sym>[A-Za-z]{1,5}(?:\.[A-Za-z])?)\b",
    re.I,
)
_PREFER = re.compile(
    r"\b(?:prefer|favou?r|focus on|mostly|mainly|stick (?:to|with)|only)\s+(?P<what>[A-Za-z][A-Za-z ,/&\-]{0,60})",
    re.I,
)


def _money(match: re.Match[str]) -> Decimal | None:
    groups = match.groupdict()
    raw = next((groups[k] for k in ("a1", "b1", "a2", "b2") if groups.get(k)), None)
    suffix = next((groups[k] for k in ("ak1", "bk1", "ak2", "bk2") if groups.get(k)), "").lower()
    if raw is None:
        return None
    try:
        amount = Decimal(raw.replace(",", ""))
    except InvalidOperation:
        return None
    return amount * {"": 1, "k": 1000, "m": 1_000_000}[suffix]


def _horizon_days(text: str) -> int | None:
    lowered = text.lower()
    best: int | None = None
    for match in _HORIZON.finditer(lowered):
        # "$200 a month" / "per year" are rates, not horizons: require the number to stand alone.
        before = lowered[max(0, match.start() - 8) : match.start()]
        if re.search(r"(\$|%|per|a|/)\s*$", before):
            continue
        if (
            re.search(
                r"\b(for|over|within|in|next|horizon of|plan|time ?frame|outlook)\b",
                lowered[max(0, match.start() - 24) : match.start()],
            )
            or re.search(r"-\s*(year|month|week|day)", match.group(0))
            or match.group(0).strip().endswith(("horizon", "plan", "growth", "outlook", "frame"))
        ):
            unit = {"day": 1, "week": 7, "month": 30, "year": 365}[match.group("u").lower()]
            days = round(float(match.group("n")) * unit)
            if 1 <= days <= 36_500:
                best = days
    if best is None:
        if re.search(r"\blong[- ]term\b", lowered):
            return 1826
        if re.search(r"\bshort[- ]term\b", lowered):
            return 30
    return best


def _classes_in(phrase: str) -> set[AssetClass]:
    found: set[AssetClass] = set()
    lowered = phrase.lower()
    for word, asset_class in _ASSET_WORDS.items():
        if re.search(rf"\b{re.escape(word)}\b", lowered):
            found.add(asset_class)
    return found


def _tickers(text: str) -> tuple[str, ...]:
    seen: list[str] = []
    for token in _TICKER.findall(text):
        if token in _NOT_TICKERS or token in seen:
            continue
        seen.append(token)
    return tuple(seen)


def parse_instruction(text: str, current: StrategyProfile) -> ParsedInstruction:  # noqa: C901
    """Turn free text into structured, bounded proposals. Never mutates anything."""

    cleaned = " ".join(text.split())[:MAX_TEXT_LENGTH]
    lowered = cleaned.lower()
    persistence = Persistence.PERSISTENT
    if _TEMPORARY.search(cleaned) and not _PERSISTENT.search(cleaned):
        persistence = Persistence.TEMPORARY

    changes: list[ProposedChange] = []
    goals: list[GoalDraft] = []
    warnings: list[str] = []
    contradictions: list[Contradiction] = []
    intents: list[InstructionIntent] = []
    context: dict[str, object] = {}

    def propose(
        field: str, old: object, new: object, description: str, *, hard: bool = False
    ) -> None:
        if old == new:
            return
        changes.append(
            ProposedChange(field, old, new, persistence, description, modifies_hard_limit=hard)
        )

    # --- risk posture ------------------------------------------------------------------------
    conservative = bool(
        re.search(
            r"\b(conservative|care[- ]?bear|low[- ]risk|cautious|safe(?:ly)?|risk[- ]averse)\b",
            lowered,
        )
    )
    aggressive = bool(
        re.search(r"\b(aggressive|hawk(?:ish)?|high[- ]risk|risk[- ]seeking|bold)\b", lowered)
    )
    if conservative and aggressive:
        contradictions.append(
            Contradiction(
                "The instruction asks for both a conservative and an aggressive posture.",
                ("risk_tolerance",),
            )
        )
    elif conservative:
        propose(
            "risk_tolerance",
            current.risk_tolerance.value,
            "conservative",
            "Use a conservative (Care-Bear) risk tolerance.",
        )
    elif aggressive:
        propose(
            "risk_tolerance",
            current.risk_tolerance.value,
            "aggressive",
            "Use an aggressive (Hawkish) risk tolerance.",
        )
    if re.search(r"\bmoderate\b", lowered) and not (conservative or aggressive):
        propose(
            "risk_tolerance",
            current.risk_tolerance.value,
            "moderate",
            "Use a moderate risk tolerance.",
        )

    # --- horizon -----------------------------------------------------------------------------
    days = _horizon_days(cleaned)
    if days is not None:
        propose(
            "horizon_days", current.horizon_days, days, f"Use an investment horizon of {days} days."
        )

    # --- hard limits -------------------------------------------------------------------------
    match = _DRAWDOWN.search(cleaned)
    if match:
        rate = float(match.group("d")) / 100.0
        if 0.0 < rate <= 1.0:
            propose(
                "max_drawdown_rate",
                current.max_drawdown_rate,
                rate,
                f"Limit portfolio drawdown to {rate:.0%}.",
                hard=True,
            )
        else:
            warnings.append("A drawdown limit must be between 0% and 100%; it was ignored.")
    match = _RESERVE.search(cleaned)
    if match:
        rate = float(match.group("c") or match.group("c2")) / 100.0
        if 0.0 <= rate < 1.0:
            propose(
                "cash_reserve_rate",
                current.cash_reserve_rate,
                rate,
                f"Keep at least {rate:.0%} of the portfolio in cash.",
                hard=True,
            )
        else:
            warnings.append("A cash reserve must be below 100%; it was ignored.")
    match = _POSITION.search(cleaned)
    if not (
        match
        and re.search(
            r"(stock|position|holding|asset|company|name|one|single|any)", match.group(0), re.I
        )
    ):
        match = _POSITION_AFTER.search(cleaned)
    if match and re.search(
        r"(stock|position|holding|asset|company|name|one|single|any)", match.group(0), re.I
    ):
        rate = float(match.group("w")) / 100.0
        if 0.0 < rate <= 1.0:
            propose(
                "max_position_weight",
                current.max_position_weight,
                rate,
                f"Cap any single position at {rate:.0%}.",
                hard=True,
            )
    match = _VOL_CAP.search(cleaned)
    if match:
        propose(
            "max_annualized_volatility",
            current.max_annualized_volatility,
            float(match.group("v")) / 100.0,
            f"Avoid assets with volatility above {float(match.group('v')):.0f}%.",
            hard=True,
        )

    # --- exclusions / preferences ------------------------------------------------------------
    excluded_symbols = set(current.excluded_symbols)
    prohibited = set(current.constraints.prohibited_asset_classes)
    new_excluded: set[str] = set()
    new_prohibited: set[AssetClass] = set()
    for exc in _EXCLUDE.finditer(cleaned):
        phrase = exc.group("what")
        new_prohibited |= _classes_in(phrase)
        new_excluded |= set(_tickers(phrase))
    already: list[str] = []
    if new_excluded and not (new_excluded - excluded_symbols):
        already.append(f"{', '.join(sorted(new_excluded))} is already excluded.")
    if new_prohibited and not (new_prohibited - prohibited):
        already.append(
            f"{', '.join(sorted(c.value for c in new_prohibited))} is already prohibited."
        )
    if new_excluded - excluded_symbols:
        merged = sorted(excluded_symbols | new_excluded)
        propose(
            "excluded_symbols",
            sorted(excluded_symbols),
            merged,
            f"Exclude {', '.join(sorted(new_excluded))}.",
            hard=True,
        )
    if new_prohibited - prohibited:
        merged_classes = sorted(c.value for c in prohibited | new_prohibited)
        propose(
            "prohibited_asset_classes",
            sorted(c.value for c in prohibited),
            merged_classes,
            f"Prohibit {', '.join(sorted(c.value for c in new_prohibited))}.",
            hard=True,
        )
    pref = _PREFER.search(cleaned)
    if pref:
        preferred = _classes_in(pref.group("what")) - new_prohibited
        if preferred and set(preferred) != set(current.preferred_asset_classes):
            propose(
                "preferred_asset_classes",
                sorted(c.value for c in current.preferred_asset_classes),
                sorted(c.value for c in preferred),
                f"Prefer {', '.join(sorted(c.value for c in preferred))}.",
            )
    if re.search(r"\bdividend|income\b", lowered) and re.search(
        r"\bprefer|focus|mostly|mainly|want\b", lowered
    ):
        propose(
            "income_weight",
            current.income_weight,
            0.7,
            "Weight dividend/income assets more heavily (income weight 0.7).",
        )
    freq = re.search(
        r"\b(trade|trading)\s+(?:only\s+)?(daily|weekly|monthly|rarely|infrequently|often|frequently)\b",
        lowered,
    )
    if freq:
        mapping = {
            "daily": "high",
            "often": "high",
            "frequently": "high",
            "weekly": "medium",
            "monthly": "low",
            "rarely": "low",
            "infrequently": "low",
        }
        propose(
            "trading_frequency",
            current.trading_frequency.value,
            mapping[freq.group(2)],
            f"Trade {freq.group(2)}.",
        )

    # --- goals -------------------------------------------------------------------------------
    capital: Decimal | None = None
    cap_match = _CAPITAL.search(cleaned)
    if cap_match:
        capital = _money_simple(cap_match)
        if capital is not None:
            context["starting_capital"] = str(capital)
    for m in _AMOUNT_PER.finditer(cleaned):
        amount = _money(m)
        period = _PERIOD_WORDS.get((m.group("p") or m.group("pw") or "").lower())
        if amount is None or period is None or amount <= 0:
            continue
        basis = (
            "investment_income"
            if re.search(r"dividend|income|yield", lowered)
            else (
                "realized_profit"
                if re.search(r"profit|earn|make|gain|realized|withdraw", lowered)
                else "total_return"
            )
        )
        goals.append(
            GoalDraft(
                name=f"{amount:,.2f} per {_PERIOD_LABEL[period]} ({basis.replace('_', ' ')})",
                target_amount=str(amount),
                period=period,
                basis=basis,
                horizon_years=(days / 365.0) if days else None,
                starting_capital=str(capital) if capital is not None else None,
            )
        )
    for m in _RATE_PER_YEAR.finditer(cleaned):
        rate = float(m.group("r")) / 100.0
        if 0.0 <= rate < 5.0:
            goals.append(
                GoalDraft(
                    name=f"{rate:.1%}/year return",
                    target_annual_rate=rate,
                    basis="total_return",
                    horizon_years=(days / 365.0) if days else None,
                    starting_capital=str(capital) if capital is not None else None,
                )
            )
    if re.search(
        r"capital preservation|preserve (?:my )?capital|don'?t lose (?:my )?(?:money|capital)",
        lowered,
    ) and not any(g.target_annual_rate == 0.0 for g in goals):
        goals.append(
            GoalDraft(
                name="Capital preservation",
                target_annual_rate=0.0,
                basis="total_return",
                horizon_years=(days / 365.0) if days else None,
                starting_capital=str(capital) if capital is not None else None,
            )
        )

    orders: list[OrderDraft] = []
    for om in _ORDER.finditer(cleaned):
        symbol = om.group("sym").upper()
        if symbol in _NOT_TICKERS or symbol in {
            "MORE",
            "LESS",
            "SOME",
            "ANY",
            "MY",
            "THAT",
            "THIS",
            "IT",
            "SHARES",
            "SHARE",
            "WORTH",
            "OF",
        }:
            continue
        verb = om.group("side").lower()
        side = {"sell": "sell", "short": "short", "cover": "cover"}.get(verb, "buy")
        quantity = notional = None
        close = False
        if om.group("qty"):
            quantity = om.group("qty")
        elif om.group("amt"):
            amount = Decimal(om.group("amt").replace(",", "")) * (1000 if om.group("k") else 1)
            notional = str(amount)
        elif om.group("all"):
            close = side in {"sell", "cover"}
            if not close:
                warnings.append(
                    f"'{side.capitalize()} all' is ambiguous and was ignored; specify a quantity "
                    "or amount."
                )
                continue
        orders.append(OrderDraft(side, symbol, quantity, notional, close))
    if orders:
        context["note_orders"] = "Simulated orders run only after you confirm them."

    # --- intents -----------------------------------------------------------------------------
    symbols = tuple(s for s in _tickers(cleaned) if s not in new_excluded)
    if goals:
        intents.append(InstructionIntent.SET_GOAL)
    if orders:
        intents.append(InstructionIntent.PLACE_ORDER)
    if changes:
        intents.append(InstructionIntent.SET_PREFERENCE)
    if re.search(
        r"\b(analy[sz]e|review|check|assess|look at)\b.*\b(portfolio|holdings|positions)\b", lowered
    ):
        intents.append(InstructionIntent.ANALYZE_PORTFOLIO)
    if re.search(r"\b(on track|feasible|achievable|realistic|reach|hit|meet)\b", lowered) and goals:
        intents.append(InstructionIntent.EVALUATE_GOAL)
    if re.search(
        r"\b(allocate|allocation|how (?:should|do) i (?:invest|split|spread|divide))\b", lowered
    ):
        intents.append(InstructionIntent.SUGGEST_ALLOCATION)
    if re.search(r"\b(find|suggest|recommend|ideas?|which (?:stocks?|etfs?))\b", lowered):
        intents.append(InstructionIntent.FIND_INVESTMENTS)
    if re.search(r"\bexplain|why\b", lowered):
        intents.append(InstructionIntent.EXPLAIN)
    if not intents:
        intents.append(
            InstructionIntent.QUESTION if _QUESTION.search(cleaned) else InstructionIntent.QUESTION
        )

    # --- contradictions ------------------------------------------------------------------------
    rate_goal = max(
        (g.target_annual_rate for g in goals if g.target_annual_rate is not None), default=None
    )
    new_risk = next(
        (c.new_value for c in changes if c.field == "risk_tolerance"), current.risk_tolerance.value
    )
    new_dd = next(
        (c.new_value for c in changes if c.field == "max_drawdown_rate"), current.max_drawdown_rate
    )
    if rate_goal is not None and rate_goal >= 0.15 and new_risk == "conservative":
        contradictions.append(
            Contradiction(
                f"A {rate_goal:.0%} annual target is hard to reconcile with a conservative risk posture.",
                ("risk_tolerance", "target_annual_rate"),
            )
        )
    if rate_goal is not None and rate_goal >= 0.15 and new_dd is not None and new_dd <= 0.10:
        contradictions.append(
            Contradiction(
                f"A {rate_goal:.0%} annual target conflicts with a drawdown limit of {new_dd:.0%}.",
                ("max_drawdown_rate", "target_annual_rate"),
            )
        )
    if new_risk == "aggressive" and new_dd is not None and new_dd <= 0.08:
        contradictions.append(
            Contradiction(
                f"An aggressive posture and a {new_dd:.0%} drawdown limit pull in opposite directions.",
                ("risk_tolerance", "max_drawdown_rate"),
            )
        )
    if re.search(r"\b(all[- ]in|everything|fully invested|100\s*%\s*invested)\b", lowered):
        reserve = next(
            (c.new_value for c in changes if c.field == "cash_reserve_rate"),
            current.cash_reserve_rate,
        )
        if reserve and reserve > 0:
            contradictions.append(
                Contradiction(
                    "Being fully invested contradicts a cash reserve.", ("cash_reserve_rate",)
                )
            )
    held_and_excluded = [s for s in symbols if s in new_excluded]
    if held_and_excluded:
        contradictions.append(
            Contradiction(
                f"{', '.join(held_and_excluded)} is both excluded and referenced as an investment.",
                ("excluded_symbols",),
            )
        )
    short_goal = (
        days is not None
        and days <= 30
        and new_risk == "conservative"
        and rate_goal is not None
        and rate_goal >= 0.10
    )
    if short_goal:
        contradictions.append(
            Contradiction(
                "A very short horizon with a conservative posture rarely supports a high return target.",
                ("horizon_days", "risk_tolerance"),
            )
        )

    if persistence is Persistence.TEMPORARY and changes:
        context["note"] = "Temporary: applies to this analysis only and is not saved."
    if (
        not (changes or goals or orders or symbols)
        and intents == [InstructionIntent.QUESTION]
        and not already
    ):
        return ParsedInstruction(
            cleaned,
            tuple(intents),
            unrecognised=True,
            warnings=("No settings or goals were recognised in the instruction.",),
        )
    return ParsedInstruction(
        text=cleaned,
        intents=tuple(dict.fromkeys(intents)),
        changes=tuple(changes),
        goal_drafts=tuple(goals),
        order_drafts=tuple(orders),
        symbols=symbols,
        contradictions=tuple(contradictions),
        warnings=tuple(warnings),
        already_in_effect=tuple(already),
        temporary_context=context,
    )


def _money_simple(match: re.Match[str]) -> Decimal | None:
    try:
        amount = Decimal(match.group("a").replace(",", ""))
    except InvalidOperation:
        return None
    suffix = (match.group("k") or "").lower()
    return amount * {"": 1, "k": 1000, "m": 1_000_000}[suffix]


def describe_fields(fields: Iterable[str]) -> str:
    return ", ".join(sorted(set(fields)))
