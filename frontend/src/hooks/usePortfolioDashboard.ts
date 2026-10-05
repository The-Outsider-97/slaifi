import { useCallback, useEffect, useState } from "react";

import { createRequestId, fetchCurrentPortfolio } from "../services/api";
import type { PortfolioAnalysisResponse } from "../types/market";

export function usePortfolioDashboard() {
  const [portfolio, setPortfolio] = useState<PortfolioAnalysisResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [insightLoading, setInsightLoading] = useState(false);
  const [insightError, setInsightError] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);

    try {
      const result = await fetchCurrentPortfolio(false, signal);
      setPortfolio(result);
      setInsightError(null);
    } catch (reason: unknown) {
      if (signal?.aborted) return;
      setPortfolio(null);
      setError(reason instanceof Error ? reason.message : "Unable to load portfolio");
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  const requestInsight = useCallback(async () => {
    if (!portfolio) return;
    setInsightLoading(true);
    setInsightError(null);

    try {
      const result = await fetchCurrentPortfolio(true, undefined, createRequestId());
      if (result) {
        setPortfolio(result);
      } else {
        setInsightError("Portfolio state is no longer available.");
      }
    } catch (reason: unknown) {
      setInsightError(
        reason instanceof Error
          ? reason.message
          : "Unable to request SLAI portfolio reasoning",
      );
    } finally {
      setInsightLoading(false);
    }
  }, [portfolio]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  return {
    portfolio,
    loading,
    error,
    insightLoading,
    insightError,
    refresh: () => void load(),
    requestInsight: () => void requestInsight(),
  };
}
