"""Deterministic TEST DOUBLE for the market-data provider contract.

It lives in tests/ and is never shipped or importable from the application. It lets the suite
exercise the complete workflow without network access or API keys. The numbers are synthetic;
the application itself has no mock mode.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from slaifi.core.types import CurrencyCode
from slaifi.domain.assets import AssetClass, AssetId
from slaifi.domain.market import ProviderPolicy
from slaifi.domain.market.models import AssetRef, InstrumentInfo, OHLCVBar, PriceQuote
from slaifi.infrastructure.market_data.base import RequestBudget

_ANCHOR = datetime(2018, 1, 1, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class _Spec:
    symbol: str
    name: str
    asset_class: AssetClass
    exchange: str
    base_price: str
    annual_drift: float
    annual_vol: float
    country: str = "United States"
    instrument_type: str = "Common Stock"
    legacy_change_percent: str | None = None


_CATALOG: tuple[_Spec, ...] = (
    _Spec(
        "SPY",
        "SPDR S&P 500 ETF Trust",
        AssetClass.ETF,
        "NYSE",
        "100.00",
        0.08,
        0.16,
        instrument_type="ETF",
        legacy_change_percent="0.42",
    ),
    _Spec(
        "QQQ",
        "Invesco QQQ Trust",
        AssetClass.ETF,
        "NASDAQ",
        "200.00",
        0.10,
        0.21,
        instrument_type="ETF",
        legacy_change_percent="-0.18",
    ),
    _Spec(
        "DIA",
        "SPDR Dow Jones Industrial Average ETF",
        AssetClass.ETF,
        "NYSE",
        "150.00",
        0.07,
        0.15,
        instrument_type="ETF",
        legacy_change_percent="0.11",
    ),
    _Spec(
        "VIX",
        "CBOE Volatility Index",
        AssetClass.INDEX,
        "CBOE",
        "20.00",
        0.0,
        0.55,
        instrument_type="Index",
        legacy_change_percent="0.00",
    ),
    _Spec("AAPL", "Apple Inc.", AssetClass.EQUITY, "NASDAQ", "180.00", 0.14, 0.28),
    _Spec(
        "MSFT",
        "Microsoft Corporation",
        AssetClass.EQUITY,
        "NASDAQ",
        "380.00",
        0.15,
        0.26,
    ),
    _Spec(
        "GOOGL",
        "Alphabet Inc. Class A",
        AssetClass.EQUITY,
        "NASDAQ",
        "140.00",
        0.12,
        0.29,
    ),
    _Spec("AMZN", "Amazon.com, Inc.", AssetClass.EQUITY, "NASDAQ", "170.00", 0.13, 0.33),
    _Spec(
        "NVDA",
        "NVIDIA Corporation",
        AssetClass.EQUITY,
        "NASDAQ",
        "450.00",
        0.30,
        0.50,
    ),
    _Spec("TSLA", "Tesla, Inc.", AssetClass.EQUITY, "NASDAQ", "240.00", 0.10, 0.58),
    _Spec("JNJ", "Johnson & Johnson", AssetClass.EQUITY, "NYSE", "155.00", 0.05, 0.16),
    _Spec("KO", "The Coca-Cola Company", AssetClass.EQUITY, "NYSE", "60.00", 0.05, 0.15),
    _Spec(
        "BND",
        "Vanguard Total Bond Market ETF",
        AssetClass.ETF,
        "NASDAQ",
        "72.00",
        0.02,
        0.06,
        instrument_type="ETF",
    ),
    _Spec(
        "GLD",
        "SPDR Gold Shares",
        AssetClass.ETF,
        "NYSE",
        "185.00",
        0.04,
        0.14,
        instrument_type="ETF",
    ),
    _Spec(
        "BTC/USD",
        "Bitcoin / US Dollar",
        AssetClass.CRYPTO,
        "Coinbase",
        "40000.00",
        0.20,
        0.70,
        instrument_type="Digital Currency",
    ),
)
_BY_SYMBOL = {spec.symbol: spec for spec in _CATALOG}
_DEFAULT = _Spec(
    "?",
    "Unknown instrument",
    AssetClass.UNKNOWN,
    "",
    "50.00",
    0.05,
    0.25,
    instrument_type="Unknown",
)


def _uniform(symbol: str, ordinal: int, salt: int) -> float:
    digest = hashlib.sha256(f"{symbol}|{ordinal}|{salt}".encode()).digest()
    return (int.from_bytes(digest[:8], "big") + 1) / (2**64 + 2)


def _shock(symbol: str, ordinal: int) -> float:
    """Deterministic standard-normal draw (Box-Muller) for one symbol-day."""

    u1, u2 = _uniform(symbol, ordinal, 1), _uniform(symbol, ordinal, 2)
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def _is_trading_day(day: datetime) -> bool:
    return day.weekday() < 5


class SyntheticFeed:
    """Deterministic synthetic provider; duck-types the adapters the gateway drives."""

    name = "testfeed"
    label = "Test feed"
    capabilities: tuple[str, ...] = ("quotes", "bars", "search")
    supported_intervals: tuple[str, ...] = ("1day",)
    data_mode = "live"

    def __init__(self) -> None:
        self.policy = ProviderPolicy(note="test double")
        self.budget = RequestBudget(self.policy)
        self.calls = 0

    async def close(self) -> None:
        return None

    # ----------------------------------------------------------------- search
    async def search_instruments(self, query: str, *, limit: int = 10) -> Sequence[InstrumentInfo]:
        needle = query.strip().lower()
        if not needle:
            return ()
        hits: list[InstrumentInfo] = []
        for spec in _CATALOG:
            if needle in spec.symbol.lower() or needle in spec.name.lower():
                hits.append(
                    InstrumentInfo(
                        asset=AssetId(
                            spec.symbol, spec.asset_class, spec.exchange, CurrencyCode("USD")
                        ),
                        name=spec.name,
                        country=spec.country,
                        instrument_type=spec.instrument_type,
                    )
                )
        hits.sort(key=lambda info: (info.asset.symbol.lower() != needle, info.asset.symbol))
        return tuple(hits[: max(1, limit)])

    # ----------------------------------------------------------------- quotes
    async def get_quotes(self, assets: Sequence[AssetRef]) -> Sequence[PriceQuote]:
        self.calls += 1
        observed_at = datetime.now(UTC)
        return [self._quote(a, observed_at) for a in assets if a.symbol in _BY_SYMBOL]

    def _quote(self, asset: AssetRef, observed_at: datetime) -> PriceQuote:
        spec = _BY_SYMBOL.get(asset.symbol, _DEFAULT)
        base = Decimal(spec.base_price)
        change_rate: float | None
        previous: Decimal | None = None
        if spec is not _DEFAULT:
            closes = self._closes(spec, observed_at, 2)
            price = closes[-1]
            previous = closes[-2] if len(closes) > 1 else None
            change_rate = float(price / previous - 1) if previous else None
            if spec.legacy_change_percent is not None:
                change_rate = float(Decimal(spec.legacy_change_percent) / Decimal("100"))
        else:
            price = base
            change_rate = (
                float(Decimal(spec.legacy_change_percent) / Decimal("100"))
                if spec.legacy_change_percent
                else (0.0 if spec is _DEFAULT else None)
            )
        return PriceQuote(
            asset=asset,
            price=price,
            change_rate=change_rate,
            currency=CurrencyCode("USD"),
            observed_at=observed_at,
            source="testfeed",
            is_market_open=None,
            delayed=False,
            previous_close=previous,
        )

    # ----------------------------------------------------------------- history
    async def get_bars(
        self,
        asset: AssetRef,
        *,
        start_at: datetime,
        end_at: datetime,
        interval: str = "1day",
    ) -> Sequence[OHLCVBar]:
        self.calls += 1
        if interval != "1day":
            return ()
        spec = _BY_SYMBOL.get(asset.symbol)
        if spec is None:
            return ()
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        days = self._trading_days(today)
        closes = self._price_path(spec, days)
        bars: list[OHLCVBar] = []
        for index, (day, close) in enumerate(zip(days, closes, strict=True)):
            if day < start_at.replace(hour=0, minute=0, second=0, microsecond=0) or day > end_at:
                continue
            previous = closes[index - 1] if index else close
            ordinal = (day - _ANCHOR).days
            gap = Decimal(str(round(0.002 * _shock(spec.symbol, ordinal + 10_000), 6)))
            open_price = max(
                Decimal("0.01"), (previous * (Decimal(1) + gap)).quantize(Decimal("0.0001"))
            )
            spread = Decimal(
                str(abs(round(0.006 * _shock(spec.symbol, ordinal + 20_000), 6)))
            ) + Decimal("0.001")
            high = max(open_price, close) * (Decimal(1) + spread)
            low = min(open_price, close) * (Decimal(1) - spread)
            volume = Decimal(int(1_000_000 * (0.6 + _uniform(spec.symbol, ordinal, 3))))
            bars.append(
                OHLCVBar(
                    asset=asset,
                    start_at=day,
                    end_at=day + timedelta(days=1),
                    open=open_price,
                    high=high.quantize(Decimal("0.0001")),
                    low=low.quantize(Decimal("0.0001")),
                    close=close,
                    volume=volume,
                )
            )
        return tuple(bars)

    def _closes(self, spec: _Spec, now: datetime, count: int) -> list[Decimal]:
        today = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        days = self._trading_days(today)
        return self._price_path(spec, days)[-count:]

    @staticmethod
    def _trading_days(today: datetime) -> list[datetime]:
        days: list[datetime] = []
        day = _ANCHOR
        while day <= today:
            if _is_trading_day(day):
                days.append(day)
            day += timedelta(days=1)
        return days

    @staticmethod
    def _price_path(spec: _Spec, days: list[datetime]) -> list[Decimal]:
        """Closing path scaled so the most recent close equals the catalogue base price."""

        daily_drift = spec.annual_drift / 252.0
        daily_vol = spec.annual_vol / math.sqrt(252.0)
        level = 0.0
        raw: list[float] = []
        for day in days:
            ordinal = (day - _ANCHOR).days
            level += daily_drift - 0.5 * daily_vol**2 + daily_vol * _shock(spec.symbol, ordinal)
            raw.append(level)
        base = float(Decimal(spec.base_price))
        return [Decimal(str(round(base * math.exp(value - raw[-1]), 4))) for value in raw]
