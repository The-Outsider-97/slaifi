import type {
  MarketAnalysisRequest,
  MarketAnalysisResponse,
  MarketHistory,
  MarketOverview,
  MarketRange,
  PortfolioAnalysisResponse,
  SlaiRuntimeStatus,
} from "../types/market";

// Built UI is served by the API itself (same origin). `npm run dev` runs on another port, so it
// talks to the local API directly. VITE_API_BASE_URL overrides both.
const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? "http://127.0.0.1:8000" : "");

const RANGE_DAYS: Record<MarketRange, number> = {
  "1W": 7,
  "1M": 31,
  "3M": 93,
  "1Y": 366,
};

export function createRequestId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `slaifi-ui-${crypto.randomUUID()}`;
  }
  return `slaifi-ui-${Date.now()}`;
}

/** An HTTP failure with the status and the server's explanation kept apart from the message. */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  readonly code: string;

  constructor(message: string, status: number, detail: string, code: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.code = code;
  }
}

/** The text to show a person: the server's detail when there is one, otherwise a plain fallback. */
export function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.detail || `The request failed (status ${error.status}).`;
  if (error instanceof Error) return error.name === "AbortError" ? "" : error.message;
  return "Something went wrong.";
}

async function responseError(response: Response, path: string): Promise<Error> {
  let detail = "";
  let code = "";
  try {
    const body = (await response.json()) as { detail?: unknown; error?: string };
    code = body.error ?? "";
    if (typeof body.detail === "string") {
      detail = body.detail;
    } else if (Array.isArray(body.detail)) {
      detail = body.detail
        .map((item) => (item && typeof item === "object" && "msg" in item ? String((item as { msg: unknown }).msg) : ""))
        .filter(Boolean)
        .join("; ");
    } else {
      detail = body.error ?? "";
    }
  } catch {
    detail = "";
  }
  return new ApiError(
    `${path} request failed with status ${response.status}${detail ? `: ${detail}` : ""}`,
    response.status,
    detail,
    code,
  );
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });
  if (!response.ok) throw await responseError(response, path);
  return (await response.json()) as T;
}

async function apiRequestNullable<T>(path: string, init: RequestInit = {}): Promise<T | null> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { Accept: "application/json", ...init.headers },
  });
  if (response.status === 204) return null;
  if (!response.ok) throw await responseError(response, path);
  return (await response.json()) as T;
}

export function fetchMarketOverview(signal?: AbortSignal): Promise<MarketOverview> {
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

export function fetchSlaiStatus(signal?: AbortSignal): Promise<SlaiRuntimeStatus> {
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
  requestId?: string,
): Promise<PortfolioAnalysisResponse | null> {
  const query = new URLSearchParams({ include_reasoning: String(includeReasoning) });
  return apiRequestNullable<PortfolioAnalysisResponse>(
    `/api/v1/portfolio/current?${query.toString()}`,
    {
      signal,
      headers: requestId ? { "X-Request-ID": requestId } : undefined,
    },
  );
}
