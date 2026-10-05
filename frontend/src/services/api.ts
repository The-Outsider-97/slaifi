import type {
  MarketAnalysisRequest,
  MarketAnalysisResponse,
  MarketHistory,
  MarketOverview,
  MarketRange,
  PortfolioAnalysisResponse,
  SlaiRuntimeStatus,
} from "../types/market";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  "http://127.0.0.1:8000";

const RANGE_DAYS: Record<MarketRange, number> = {
  "1W": 7,
  "1M": 31,
  "3M": 93,
  "1Y": 366,
};

async function responseError(
  response: Response,
  path: string,
): Promise<Error> {
  let detail = "";

  try {
    const body = (await response.json()) as {
      detail?: string;
      error?: string;
    };
    detail = body.detail ?? body.error ?? "";
  } catch {
    detail = "";
  }

  return new Error(
    `${path} request failed with status ${response.status}${detail ? `: ${detail}` : ""}`,
  );
}

async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });

  if (!response.ok) {
    throw await responseError(response, path);
  }

  return (await response.json()) as T;
}

async function apiRequestNullable<T>(
  path: string,
  init: RequestInit = {},
): Promise<T | null> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...init.headers,
    },
  });

  if (response.status === 204) {
    return null;
  }

  if (!response.ok) {
    throw await responseError(response, path);
  }

  return (await response.json()) as T;
}

export function fetchMarketOverview(
  signal?: AbortSignal,
): Promise<MarketOverview> {
  return apiRequest<MarketOverview>("/api/v1/market/overview", { signal });
}

export function fetchMarketHistory(
  symbol: string,
  assetClass: string,
  range: MarketRange,
  signal?: AbortSignal,
): Promise<MarketHistory> {
  const query = new URLSearchParams({
    days: String(RANGE_DAYS[range]),
    asset_class: assetClass,
  });

  return apiRequest<MarketHistory>(
    `/api/v1/market/history/${encodeURIComponent(symbol)}?${query.toString()}`,
    { signal },
  );
}

export function fetchSlaiStatus(
  signal?: AbortSignal,
): Promise<SlaiRuntimeStatus> {
  return apiRequest<SlaiRuntimeStatus>("/api/v1/integrations/slai", { signal });
}

export function analyzeMarket(
  payload: MarketAnalysisRequest,
  requestId: string,
): Promise<MarketAnalysisResponse> {
  return apiRequest<MarketAnalysisResponse>("/api/v1/analysis/market", {
    method: "POST",
    headers: { "X-Request-ID": requestId },
    body: JSON.stringify(payload),
  });
}

export function fetchCurrentPortfolio(
  includeReasoning = false,
  signal?: AbortSignal,
): Promise<PortfolioAnalysisResponse | null> {
  const query = new URLSearchParams({
    include_reasoning: String(includeReasoning),
  });

  return apiRequestNullable<PortfolioAnalysisResponse>(
    `/api/v1/portfolio/current?${query.toString()}`,
    { signal },
  );
}
