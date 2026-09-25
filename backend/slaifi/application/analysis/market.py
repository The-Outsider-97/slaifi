"""Orchestrate deterministic market calculations and optional SLAI interpretation."""

from collections.abc import Sequence

from slaifi.application.contracts import FinancialReasoner, ReasoningRequest
from slaifi.application.models import MarketAnalysisResult, TechnicalMeasurements
from slaifi.core.exceptions import InsufficientDataError, ValidationError
from slaifi.domain.assets import AssetId
from slaifi.domain.market import OHLCVBar
from slaifi.engines.features import calculations as features
from slaifi.engines.risk import maximum_drawdown
from slaifi.engines.technical import indicators


class AnalyzeMarketSeries:
    """Analyze normalized chronological OHLCV observations without fetching data."""

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
        highs = [float(bar.high) for bar in bars]
        lows = [float(bar.low) for bar in bars]
        volumes = [float(bar.volume) for bar in bars]
        simple = features.simple_returns(closes)
        drawdowns = features.drawdown(closes)
        rolling_vol = features.rolling_volatility(
            closes,
            moving_average_period,
            periods_per_year=periods_per_year,
        )
        sma_series = indicators.sma(closes, moving_average_period)
        ema_series = indicators.ema(closes, moving_average_period)
        momentum_series = indicators.momentum(closes, momentum_period)
        rsi_series = indicators.rsi(closes, rsi_period)
        macd_line, signal_line, _ = indicators.macd(closes)
        atr_series = indicators.atr(highs, lows, closes, atr_period)

        result = MarketAnalysisResult(
            symbol=asset.display_symbol,
            observation_count=len(bars),
            latest_close=closes[-1],
            simple_return=simple[-1],
            rolling_volatility=rolling_vol[-1],
            maximum_drawdown=maximum_drawdown(closes),
            technical=TechnicalMeasurements(
                sma=sma_series[-1],
                ema=ema_series[-1],
                momentum=momentum_series[-1],
                rsi=rsi_series[-1],
                macd=macd_line[-1],
                macd_signal=signal_line[-1],
                atr=atr_series[-1],
            ),
            features={
                "simple_returns": tuple(simple),
                "drawdown": tuple(drawdowns),
                "rolling_volatility": tuple(rolling_vol),
                "volume_change": tuple(features.volume_change(volumes)),
            },
        )
        if self._reasoner is None or not reasoning_objective:
            return result

        evidence = {
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
        reasoning = self._reasoner.reason(
            ReasoningRequest(
                operation="market_analysis",
                evidence=evidence,
                objective=reasoning_objective,
                assumptions={"periods_per_year": periods_per_year},
                uncertainty={"prediction_model_used": False},
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
    def _validate_bars(bars: Sequence[OHLCVBar]) -> None:
        previous = None
        for bar in bars:
            if previous is not None and bar.end_at <= previous:
                raise ValidationError("market bars must be strictly chronological and unique")
            previous = bar.end_at
