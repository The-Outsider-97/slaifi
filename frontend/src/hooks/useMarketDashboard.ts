import { useCallback, useEffect, useState } from "react";

import { analyzeMarket, fetchMarketOverview, fetchSlaiStatus } from "../services/api";
import { buildIllustrativeMarketAnalysisRequest } from "../data/demoMarket";
import type { MarketAnalysisResponse, MarketOverview, SlaiRuntimeStatus } from "../types/market";

function newRequestId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `slaifi-ui-${crypto.randomUUID()}`;
  }
  return `slaifi-ui-${Date.now()}`;
}

export function useMarketDashboard() {
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
        setMarketError(marketResult.reason instanceof Error ? marketResult.reason.message : "Unable to load market overview");
      }
      if (slaiResult.status === "fulfilled") {
        setSlai(slaiResult.value);
        setSlaiError(null);
      } else {
        setSlaiError(slaiResult.reason instanceof Error ? slaiResult.reason.message : "Unable to query SLAI status");
        setSlai({ status: "unavailable", interpretation: null, agent: null, agent_version: null, correlation_id: null, request_id: null, warnings: ["SLAI status endpoint unavailable"] });
      }
      setLoading(false);
    });

    return () => controller.abort();
  }, []);

  const runInsight = useCallback(async () => {
    if (!slai || (slai.status !== "available" && slai.status !== "degraded")) return;
    setAnalysisLoading(true);
    setAnalysisError(null);
    try {
      const result = await analyzeMarket(buildIllustrativeMarketAnalysisRequest(), newRequestId());
      setAnalysis(result);
      if (result.reasoning) setSlai((current) => current ? { ...current, ...result.reasoning } : result.reasoning);
    } catch (reason: unknown) {
      setAnalysisError(reason instanceof Error ? reason.message : "Unable to request SLAI reasoning");
    } finally {
      setAnalysisLoading(false);
    }
  }, [slai]);

  return {
    overview,
    slai,
    loading,
    marketError,
    slaiError,
    analysis,
    analysisLoading,
    analysisError,
    runInsight,
  };
}
