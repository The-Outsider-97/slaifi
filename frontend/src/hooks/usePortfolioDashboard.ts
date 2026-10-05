import {
  useCallback,
  useEffect,
  useState,
} from "react";

import {
  fetchCurrentPortfolio,
} from "../services/api";

import type {
  PortfolioAnalysisResponse,
} from "../types/market";

export function usePortfolioDashboard() {
  const [
    portfolio,
    setPortfolio,
  ] = useState<
    PortfolioAnalysisResponse | null
  >(null);

  const [
    loading,
    setLoading,
  ] = useState(true);

  const [
    error,
    setError,
  ] = useState<string | null>(
    null,
  );

  const load = useCallback(
    async (
      signal?: AbortSignal,
    ) => {
      setLoading(true);
      setError(null);

      try {
        const result =
          await fetchCurrentPortfolio(
            signal,
          );

        setPortfolio(result);
      } catch (reason: unknown) {
        if (signal?.aborted) {
          return;
        }

        setPortfolio(null);
        setError(
          reason instanceof Error
            ? reason.message
            : "Unable to load portfolio",
        );
      } finally {
        if (!signal?.aborted) {
          setLoading(false);
        }
      }
    },
    [],
  );

  useEffect(() => {
    const controller =
      new AbortController();

    void load(controller.signal);

    return () =>
      controller.abort();
  }, [load]);

  return {
    portfolio,
    loading,
    error,
    refresh: () =>
      void load(),
  };
}
