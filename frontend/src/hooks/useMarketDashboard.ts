import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  analyzeMarket,
  fetchMarketHistory,
  fetchMarketOverview,
  fetchSlaiStatus,
} from "../services/api";

import type {
  MarketAnalysisRequest,
  MarketAnalysisResponse,
  MarketHistory,
  MarketOverview,
  MarketRange,
  SlaiRuntimeStatus,
} from "../types/market";

function newRequestId() {
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
    return `slaifi-ui-${crypto.randomUUID()}`;
  }

  return `slaifi-ui-${Date.now()}`;
}

function buildAnalysisRequest(
  history: MarketHistory,
  currency?: string,
): MarketAnalysisRequest {
  return {
    asset: {
      symbol: history.symbol,
      asset_class: history.asset_class,
      ...(currency
        ? { currency }
        : {}),
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
      "Explain the current market regime, " +
      "material risk signals, trend evidence, " +
      "and uncertainty using only the supplied " +
      "market observations. Do not invent " +
      "missing evidence or future prices.",
  };
}

export function useMarketDashboard() {
  const [
    overview,
    setOverview,
  ] = useState<MarketOverview | null>(
    null,
  );

  const [
    slai,
    setSlai,
  ] = useState<SlaiRuntimeStatus | null>(
    null,
  );

  const [
    range,
    setRange,
  ] = useState<MarketRange>("3M");

  const [
    history,
    setHistory,
  ] = useState<MarketHistory | null>(
    null,
  );

  const [
    loading,
    setLoading,
  ] = useState(true);

  const [
    historyLoading,
    setHistoryLoading,
  ] = useState(false);

  const [
    marketError,
    setMarketError,
  ] = useState<string | null>(null);

  const [
    historyError,
    setHistoryError,
  ] = useState<string | null>(null);

  const [
    slaiError,
    setSlaiError,
  ] = useState<string | null>(null);

  const [
    analysis,
    setAnalysis,
  ] = useState<
    MarketAnalysisResponse | null
  >(null);

  const [
    analysisLoading,
    setAnalysisLoading,
  ] = useState(false);

  const [
    analysisError,
    setAnalysisError,
  ] = useState<string | null>(
    null,
  );

  useEffect(() => {
    const controller =
      new AbortController();

    setLoading(true);

    Promise.allSettled([
      fetchMarketOverview(
        controller.signal,
      ),
      fetchSlaiStatus(
        controller.signal,
      ),
    ]).then(
      ([marketResult, slaiResult]) => {
        if (
          controller.signal.aborted
        ) {
          return;
        }

        if (
          marketResult.status ===
          "fulfilled"
        ) {
          setOverview(
            marketResult.value,
          );
          setMarketError(null);
        } else {
          setOverview(null);
          setMarketError(
            marketResult.reason
              instanceof Error
              ? marketResult.reason.message
              : "Unable to load market overview",
          );
        }

        if (
          slaiResult.status ===
          "fulfilled"
        ) {
          setSlai(
            slaiResult.value,
          );
          setSlaiError(null);
        } else {
          setSlai(null);
          setSlaiError(
            slaiResult.reason
              instanceof Error
              ? slaiResult.reason.message
              : "Unable to query SLAI status",
          );
        }

        setLoading(false);
      },
    );

    return () =>
      controller.abort();
  }, []);

  const primaryQuote =
    overview?.quotes[0] ?? null;

  const primarySymbol =
    primaryQuote?.symbol ?? null;

  const primaryAssetClass =
    primaryQuote?.asset_class ?? null;

  useEffect(() => {
    setAnalysis(null);
    setAnalysisError(null);

    if (
      overview?.data_mode === "mock"
    ) {
      setHistory(null);
      setHistoryError(
        "Historical chart disabled while the mock provider is configured.",
      );
      return;
    }

    if (
      !primarySymbol ||
      !primaryAssetClass
    ) {
      setHistory(null);
      return;
    }

    const controller =
      new AbortController();

    setHistoryLoading(true);
    setHistoryError(null);

    fetchMarketHistory(
      primarySymbol,
      primaryAssetClass,
      range,
      controller.signal,
    )
      .then((result) => {
        if (
          controller.signal.aborted
        ) {
          return;
        }

        setHistory(result);
      })
      .catch((reason: unknown) => {
        if (
          controller.signal.aborted
        ) {
          return;
        }

        setHistory(null);
        setHistoryError(
          reason instanceof Error
            ? reason.message
            : "Unable to load market history",
        );
      })
      .finally(() => {
        if (
          !controller.signal.aborted
        ) {
          setHistoryLoading(false);
        }
      });

    return () =>
      controller.abort();
  }, [
    overview?.data_mode,
    primarySymbol,
    primaryAssetClass,
    range,
  ]);

  const hasAnalysisEvidence =
    useMemo(
      () =>
        (history?.bars.length ?? 0) >=
        2,
      [history],
    );

  const runInsight =
    useCallback(async () => {
      const connected =
        slai?.status === "available" ||
        slai?.status === "degraded";

      if (!connected) {
        setAnalysisError(
          "SLAI is not currently available.",
        );
        return;
      }

      if (
        !history ||
        history.bars.length < 2
      ) {
        setAnalysisError(
          "Real historical market evidence is required before SLAI analysis can run.",
        );
        return;
      }

      setAnalysisLoading(true);
      setAnalysisError(null);

      try {
        const result =
          await analyzeMarket(
            buildAnalysisRequest(
              history,
              primaryQuote?.currency,
            ),
            newRequestId(),
          );

        setAnalysis(result);

        if (result.reasoning) {
          setSlai((current) =>
            current
              ? {
                  ...current,
                  ...result.reasoning,
                }
              : result.reasoning,
          );
        }
      } catch (reason: unknown) {
        setAnalysisError(
          reason instanceof Error
            ? reason.message
            : "Unable to request SLAI reasoning",
        );
      } finally {
        setAnalysisLoading(false);
      }
    }, [
      slai,
      history,
      primaryQuote?.currency,
    ]);

  return {
    overview,
    slai,

    range,
    setRange,

    history,

    loading,
    historyLoading,

    marketError,
    historyError,
    slaiError,

    analysis,
    analysisLoading,
    analysisError,

    hasAnalysisEvidence,
    runInsight,
  };
}
