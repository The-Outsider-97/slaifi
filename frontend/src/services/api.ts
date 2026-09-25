import type {
  MarketAnalysisRequest,
  MarketAnalysisResponse,
  MarketOverview,
  SlaiRuntimeStatus,
} from "../types/market";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });

  if (!response.ok) {
    let detail = "";
    try {
      const body = (await response.json()) as { detail?: string; error?: string };
      detail = body.detail ?? body.error ?? "";
    } catch {
      detail = "";
    }
    throw new Error(`${path} request failed with status ${response.status}${detail ? `: ${detail}` : ""}`);
  }
  return (await response.json()) as T;
}

export function fetchMarketOverview(signal?: AbortSignal): Promise<MarketOverview> {
  return apiRequest<MarketOverview>("/api/v1/market/overview", { signal });
}

export function fetchSlaiStatus(signal?: AbortSignal): Promise<SlaiRuntimeStatus> {
  return apiRequest<SlaiRuntimeStatus>("/api/v1/integrations/slai", { signal });
}

export function analyzeMarket(payload: MarketAnalysisRequest, requestId: string): Promise<MarketAnalysisResponse> {
  return apiRequest<MarketAnalysisResponse>("/api/v1/analysis/market", {
    method: "POST",
    headers: { "X-Request-ID": requestId },
    body: JSON.stringify(payload),
  });
}
