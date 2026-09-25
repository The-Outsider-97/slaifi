"""Orchestrate deterministic market calculations and optional SLAI interpretation."""

from collections.abc import Callable, Sequence
from datetime import datetime

from slaifi.application.contracts import FinancialReasoner, ReasoningRequest
from slaifi.application.models import MarketAnalysisResult, TechnicalMeasurements
from slaifi.core.exceptions import InsufficientDataError, ValidationError
from slaifi.domain.assets import AssetId
from slaifi.domain.market import OHLCVBar
from slaifi.engines.features import calculations as features
from slaifi.engines.risk import maximum_drawdown
from slaifi.engines.technical import indicators

AlignedSeries = tuple[float | None, ...]


def _none_series(size: int) -> AlignedSeries:
    return tuple(None for _ in range(size))


def _last(values: Sequence[float | None]) -> float | None:
    return values[-1] if values else None


class AnalyzeMarketSeries:
    """Analyze supplied OHLCV data; unavailable warm-up measurements remain None."""

    def __init__(self, reasoner: FinancialReasoner | None = None) -> None:
        self._reasoner = reasoner

    def execute(
        self,
        asset: AssetId,
        bars: Sequence[OHLCVBar],
        *,
        periods_per_year: int,
        moving_average_period: int = 20,
        momentum_period: int = 10,
        rsi_period: int = 14,
        atr_period: int = 14,
        reasoning_objective: str | None = None,
    ) -> MarketAnalysisResult:
        if periods_per_year <= 0:
            raise ValidationError("periods_per_year must be positive")
        if len(bars) < 2:
            raise InsufficientDataError("market analysis requires at least two bars")
        self._validate_bars(bars)

        closes = [float(bar.close) for bar in bars]
        volumes = [float(bar.volume) for bar in bars]
        simple = features.simple_returns(closes)
        drawdowns = features.drawdown_series(closes)
        rolling_vol = self._feature_or_none(
            len(bars),
            lambda: features.rolling_volatility(
                closes,
                moving_average_period,
                periods_per_year=periods_per_year,
            ),
        )
        sma_series = self._feature_or_none(
            len(bars), lambda: indicators.sma(closes, moving_average_period)
        )
        ema_series = self._feature_or_none(
            len(bars), lambda: indicators.ema(closes, moving_average_period)
        )
        momentum_series = self._feature_or_none(
            len(bars), lambda: indicators.momentum(closes, momentum_period)
        )
        rsi_series = self._feature_or_none(
            len(bars), lambda: indicators.rsi(closes, rsi_period)
        )
        atr_series = self._feature_or_none(
            len(bars), lambda: indicators.atr(bars, atr_period)
        )
        try:
            macd_result = indicators.macd(closes)
            macd_value = _last(macd_result.macd_line)
            signal_value = _last(macd_result.signal_line)
        except InsufficientDataError:
            macd_value = None
            signal_value = None

        result = MarketAnalysisResult(
            symbol=asset.display_symbol,
            observation_count=len(bars),
            latest_close=closes[-1],
            simple_return=_last(simple),
            rolling_volatility=_last(rolling_vol),
            maximum_drawdown=maximum_drawdown(closes),
            technical=TechnicalMeasurements(
                sma=_last(sma_series),
                ema=_last(ema_series),
                momentum=_last(momentum_series),
                rsi=_last(rsi_series),
                macd=macd_value,
                macd_signal=signal_value,
                atr=_last(atr_series),
            ),
            features={
                "simple_returns": tuple(simple),
                "drawdown": tuple(drawdowns),
                "rolling_volatility": tuple(rolling_vol),
                "volume_change": tuple(features.volume_changes(volumes)),
            },
        )
        if self._reasoner is None or not reasoning_objective:
            return result
        reasoning = self._reasoner.reason(
            ReasoningRequest(
                operation="market_analysis",
                evidence=self._evidence(result),
                objective=reasoning_objective,
                assumptions={"periods_per_year": periods_per_year},
                uncertainty={
                    "prediction_model_used": False,
                    "unavailable_measurements_are_null": True,
                },
            )
        )
        return MarketAnalysisResult(
            symbol=result.symbol,
            observation_count=result.observation_count,
            latest_close=result.latest_close,
            simple_return=result.simple_return,
            rolling_volatility=result.rolling_volatility,
            maximum_drawdown=result.maximum_drawdown,
            technical=result.technical,
            features=result.features,
            reasoning=reasoning,
        )

    @staticmethod
    def _feature_or_none(
        size: int,
        calculation: Callable[[], Sequence[float | None]],
    ) -> AlignedSeries:
        try:
            return tuple(calculation())
        except InsufficientDataError:
            return _none_series(size)

    @staticmethod
    def _validate_bars(bars: Sequence[OHLCVBar]) -> None:
        previous: datetime | None = None
        for bar in bars:
            if previous is not None and bar.end_at <= previous:
                raise ValidationError("market bars must be strictly chronological and unique")
            previous = bar.end_at

    @staticmethod
    def _evidence(result: MarketAnalysisResult) -> dict[str, object]:
        return {
            "asset": result.symbol,
            "observation_count": result.observation_count,
            "latest_close": result.latest_close,
            "latest_return_rate": result.simple_return,
            "rolling_volatility": result.rolling_volatility,
            "maximum_drawdown_rate": result.maximum_drawdown,
            "technical": {
                "sma": result.technical.sma,
                "ema": result.technical.ema,
                "momentum": result.technical.momentum,
                "rsi": result.technical.rsi,
                "macd": result.technical.macd,
                "macd_signal": result.technical.macd_signal,
                "atr": result.technical.atr,
            },
        }
