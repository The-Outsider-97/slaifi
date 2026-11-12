import { useCallback, useEffect, useMemo, useState } from "react";

import {
  analyzeMarket,
  createRequestId,
  fetchMarketOverview,
  fetchSlaiStatus,
} from "../services/api";
import type {
  MarketAnalysisRequest,
  MarketAnalysisResponse,
  MarketHistory,
  MarketOverview,
  SlaiRuntimeStatus,
} from "../types/market";

function buildAnalysisRequest(
  history: MarketHistory,
  currency?: string,
): MarketAnalysisRequest {
  return {
    asset: {
      symbol: history.symbol,
      asset_class: history.asset_class,
      ...(currency ? { currency } : {}),
    },
    bars: history.bars.map((bar) => ({
      start_at: bar.start_at,
      end_at: bar.end_at,
      open: Number(bar.open),
      high: Number(bar.high),
      low: Number(bar.low),
      close: Number(bar.close),
      volume: Number(bar.volume),
    })),
    periods_per_year: 252,
    moving_average_period: 20,
    momentum_period: 10,
    rsi_period: 14,
    atr_period: 14,
    reasoning_objective:
      "Explain the current market regime, material risk signals, trend evidence, and " +
      "uncertainty using only the supplied market observations. Do not invent missing " +
      "evidence or future prices.",
  };
}

/**
 * The overview quotes, the SLAI status and the SLAI reading of the instrument on the chart.
 * The chart owns the price history; it hands the first instrument's bars here as ``history``.
 */
export function useMarketDashboard(history: MarketHistory | null) {
  const [overview, setOverview] = useState<MarketOverview | null>(null);
  const [slai, setSlai] = useState<SlaiRuntimeStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [marketError, setMarketError] = useState<string | null>(null);
  const [slaiError, setSlaiError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<MarketAnalysisResponse | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);

    Promise.allSettled([
      fetchMarketOverview(controller.signal),
      fetchSlaiStatus(controller.signal),
    ]).then(([marketResult, slaiResult]) => {
      if (controller.signal.aborted) return;

      if (marketResult.status === "fulfilled") {
        setOverview(marketResult.value);
        setMarketError(null);
      } else {
        setOverview(null);
        setMarketError(
          marketResult.reason instanceof Error
            ? marketResult.reason.message
            : "Unable to load market overview",
        );
      }

      if (slaiResult.status === "fulfilled") {
        setSlai(slaiResult.value);
        setSlaiError(null);
      } else {
        setSlai(null);
        setSlaiError(
          slaiResult.reason instanceof Error
            ? slaiResult.reason.message
            : "Unable to query SLAI status",
        );
      }
      setLoading(false);
    });

    return () => controller.abort();
  }, []);

  // A reading belongs to the instrument and range it was made for; drop it when they change.
  const evidenceKey = history ? `${history.symbol}|${history.bars.length}|${history.bars[0]?.start_at}` : "";
  useEffect(() => {
    setAnalysis(null);
    setAnalysisError(null);
  }, [evidenceKey]);

  const currency =
    overview?.quotes.find((quote) => quote.symbol === history?.symbol)?.currency ??
    overview?.quotes[0]?.currency;

  const hasAnalysisEvidence = useMemo(
    () => (history?.bars.length ?? 0) >= 2,
    [history],
  );

  const runInsight = useCallback(async () => {
    const connected = slai?.status === "available" || slai?.status === "degraded";
    if (!connected) {
      setAnalysisError("SLAI is not currently available.");
      return;
    }
    if (!history || history.bars.length < 2) {
      setAnalysisError("Real historical market evidence is required before SLAI analysis can run.");
      return;
    }

    setAnalysisLoading(true);
    setAnalysisError(null);
    try {
      const result = await analyzeMarket(
        buildAnalysisRequest(history, currency),
        createRequestId(),
      );
      setAnalysis(result);
      if (result.reasoning) {
        setSlai((current) =>
          current ? { ...current, ...result.reasoning } : result.reasoning,
        );
      }
    } catch (reason: unknown) {
      setAnalysisError(
        reason instanceof Error ? reason.message : "Unable to request SLAI reasoning",
      );
    } finally {
      setAnalysisLoading(false);
    }
  }, [slai, history, currency]);

  return {
    overview,
    slai,
    loading,
    marketError,
    slaiError,
    analysis,
    analysisLoading,
    analysisError,
    hasAnalysisEvidence,
    runInsight,
  };
}
