import { apiRequest } from "./api";
import type {
  AdvisorResponse,
  AuditEntry,
  BacktestResponse,
  CompareResponse,
  ConfirmResponse,
  Goal,
  GoalReport,
  GuidanceResponse,
  HistoryEntry,
  MarketMeta,
  OrderOutcome,
  PerformanceResponse,
  PortfolioMeta,
  PortfolioView,
  ProviderCheck,
  ProvidersResponse,
  QuoteResponse,
  Reconciliation,
  RecommendationResponse,
  SearchResponse,
  SeriesResponse,
  StatsResponse,
  StrategiesResponse,
  Strategy,
  SystemStatus,
  WatchlistResponse,
} from "../types/finance";

/** Every state-changing request carries this marker; the API refuses mutations without it. */
const CLIENT_HEADERS = { "X-SLAIFI-Client": "slaifi-web" } as const;

const V1 = "/api/v1";

function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") query.set(key, String(value));
  }
  const text = query.toString();
  return text ? `?${text}` : "";
}

function mutate<T>(method: "POST" | "PUT" | "PATCH" | "DELETE", path: string, body?: unknown): Promise<T> {
  return apiRequest<T>(path, {
    method,
    headers: { ...CLIENT_HEADERS },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

// ------------------------------------------------------------------ market data sources
export const fetchProviders = (signal?: AbortSignal) =>
  apiRequest<ProvidersResponse>(`${V1}/system/providers`, { signal });

/** Makes one real request per configured provider (spends a little of each free quota). */
export const checkProviders = () =>
  mutate<{ checks: ProviderCheck[] }>("POST", `${V1}/system/providers/check`);

// ------------------------------------------------------------------ market
export const marketMeta = (signal?: AbortSignal) => apiRequest<MarketMeta>(`${V1}/market/meta`, { signal });

export const searchInstruments = (q: string, signal?: AbortSignal) =>
  apiRequest<SearchResponse>(`${V1}/market/search${qs({ q })}`, { signal });

export const fetchQuote = (symbol: string, signal?: AbortSignal) =>
  apiRequest<QuoteResponse>(`${V1}/market/quote/${encodeURIComponent(symbol)}`, { signal });

export const fetchSeries = (
  symbol: string,
  options: { interval: string; range: string; overlays?: string[] },
  signal?: AbortSignal,
) =>
  apiRequest<SeriesResponse>(
    `${V1}/market/series/${encodeURIComponent(symbol)}${qs({
      interval: options.interval,
      range: options.range,
      overlays: options.overlays?.join(","),
    })}`,
    { signal },
  );

export const fetchStats = (symbol: string, options: { interval: string; range: string }, signal?: AbortSignal) =>
  apiRequest<StatsResponse>(`${V1}/market/stats/${encodeURIComponent(symbol)}${qs(options)}`, { signal });

export const fetchComparison = (
  symbols: string[],
  options: { interval: string; range: string },
  signal?: AbortSignal,
) => apiRequest<CompareResponse>(`${V1}/market/compare${qs({ symbols: symbols.join(","), ...options })}`, { signal });

export const fetchWatchlist = (signal?: AbortSignal) => apiRequest<WatchlistResponse>(`${V1}/market/watchlist`, { signal });
export const addToWatchlist = (symbol: string) => mutate<unknown>("POST", `${V1}/market/watchlist`, { symbol });
export const removeFromWatchlist = (symbol: string) =>
  mutate<{ removed: boolean }>("DELETE", `${V1}/market/watchlist/${encodeURIComponent(symbol)}`);

// ------------------------------------------------------------------ recommendations
export const fetchRecommendation = (
  symbol: string,
  options: { strategyId?: string | null; portfolioId?: string | null; explain?: boolean },
  signal?: AbortSignal,
) =>
  apiRequest<RecommendationResponse>(
    `${V1}/recommendations/${encodeURIComponent(symbol)}${qs({
      strategy_id: options.strategyId,
      portfolio_id: options.portfolioId,
      explain: options.explain,
    })}`,
    { signal },
  );

export const fetchBacktest = (symbol: string, strategyId?: string | null, signal?: AbortSignal) =>
  apiRequest<BacktestResponse>(`${V1}/recommendations/${encodeURIComponent(symbol)}/backtest${qs({ strategy_id: strategyId })}`, {
    signal,
  });

// ------------------------------------------------------------------ paper trading
export const listPortfolios = (signal?: AbortSignal) =>
  apiRequest<{ portfolios: PortfolioMeta[]; simulated: true }>(`${V1}/paper/portfolios`, { signal });

export const createPortfolio = (body: { name: string; starting_capital: string; currency?: string; strategy_id?: string | null }) =>
  mutate<PortfolioView>("POST", `${V1}/paper/portfolios`, body);

export const fetchPortfolio = (id: string, signal?: AbortSignal) =>
  apiRequest<PortfolioView>(`${V1}/paper/portfolios/${encodeURIComponent(id)}`, { signal });

export const setPortfolioStrategy = (id: string, strategyId: string | null) =>
  mutate<PortfolioMeta>("PUT", `${V1}/paper/portfolios/${encodeURIComponent(id)}/strategy`, { strategy_id: strategyId });

export const depositCash = (id: string, amount: string, note?: string) =>
  mutate<PortfolioView>("POST", `${V1}/paper/portfolios/${encodeURIComponent(id)}/deposit`, { amount, note });

export const withdrawCash = (id: string, amount: string, note?: string) =>
  mutate<PortfolioView>("POST", `${V1}/paper/portfolios/${encodeURIComponent(id)}/withdraw`, { amount, note });

export type OrderBody = {
  symbol: string;
  side: "buy" | "sell";
  quantity?: string;
  notional?: string;
  close_position?: boolean;
  client_order_id?: string;
};

export const previewOrder = (id: string, body: OrderBody) =>
  apiRequest<OrderOutcome>(`${V1}/paper/portfolios/${encodeURIComponent(id)}/orders/preview`, {
    method: "POST",
    body: JSON.stringify(body),
  });

export const placeOrder = (id: string, body: OrderBody) =>
  mutate<OrderOutcome>("POST", `${V1}/paper/portfolios/${encodeURIComponent(id)}/orders`, body);

export const fetchTradeHistory = (id: string, signal?: AbortSignal) =>
  apiRequest<{ entries: HistoryEntry[] }>(`${V1}/paper/portfolios/${encodeURIComponent(id)}/history`, { signal });

export const fetchPerformance = (id: string, signal?: AbortSignal) =>
  apiRequest<PerformanceResponse>(`${V1}/paper/portfolios/${encodeURIComponent(id)}/performance`, { signal });

export const resetPortfolio = (id: string, confirm: boolean, startingCapital?: string) =>
  mutate<PortfolioView>("POST", `${V1}/paper/portfolios/${encodeURIComponent(id)}/reset`, {
    confirm,
    starting_capital: startingCapital || undefined,
  });

export const reconcilePortfolio = (id: string, signal?: AbortSignal) =>
  apiRequest<Reconciliation>(`${V1}/paper/portfolios/${encodeURIComponent(id)}/reconcile`, { signal });

export const fetchGuidance = (id: string, explain: boolean, signal?: AbortSignal) =>
  apiRequest<GuidanceResponse>(`${V1}/paper/portfolios/${encodeURIComponent(id)}/guidance${qs({ explain })}`, { signal });

// ------------------------------------------------------------------ strategies and goals
export const fetchStrategies = (signal?: AbortSignal) => apiRequest<StrategiesResponse>(`${V1}/strategies`, { signal });

export const createStrategy = (body: { name: string; preset_id?: string | null; fields?: Record<string, unknown>; activate?: boolean }) =>
  mutate<Strategy>("POST", `${V1}/strategies`, body);

export const updateStrategy = (id: string, fields: Record<string, unknown>, acknowledgeLoosening: boolean) =>
  mutate<Strategy>("PATCH", `${V1}/strategies/${encodeURIComponent(id)}`, {
    fields,
    acknowledge_loosening: acknowledgeLoosening,
  });

export const activateStrategy = (id: string) => mutate<Strategy>("POST", `${V1}/strategies/${encodeURIComponent(id)}/activate`);
export const deleteStrategy = (id: string) => mutate<{ deleted: string }>("DELETE", `${V1}/strategies/${encodeURIComponent(id)}`);

export const fetchGoals = (signal?: AbortSignal) => apiRequest<{ goals: Goal[] }>(`${V1}/goal-tracker`, { signal });
export const createGoal = (body: Record<string, unknown>) => mutate<Goal>("POST", `${V1}/goal-tracker`, body);
export const deleteGoal = (id: string) => mutate<{ deleted: string }>("DELETE", `${V1}/goal-tracker/${encodeURIComponent(id)}`);
export const analyzeGoal = (id: string, body: { assumed_annual_return_rate?: number | null; portfolio_id?: string | null }) =>
  apiRequest<GoalReport>(`${V1}/goal-tracker/${encodeURIComponent(id)}/analyze`, {
    method: "POST",
    body: JSON.stringify(body),
  });

// ------------------------------------------------------------------ advisor
export const interpretInstruction = (text: string, portfolioId: string | null, explain = true) =>
  apiRequest<AdvisorResponse>(`${V1}/advisor/interpret`, {
    method: "POST",
    body: JSON.stringify({ text, portfolio_id: portfolioId, explain }),
  });

export const confirmProposal = (id: string, acknowledgements: { limits: boolean; contradictions: boolean }) =>
  mutate<ConfirmResponse>("POST", `${V1}/advisor/proposals/${encodeURIComponent(id)}/confirm`, {
    acknowledge_limit_changes: acknowledgements.limits,
    acknowledge_contradictions: acknowledgements.contradictions,
  });

export const rejectProposal = (id: string) => mutate<{ rejected: string }>("POST", `${V1}/advisor/proposals/${encodeURIComponent(id)}/reject`);

// ------------------------------------------------------------------ system
export const fetchSystemStatus = (signal?: AbortSignal) => apiRequest<SystemStatus>(`${V1}/system/status`, { signal });
export const fetchAudit = (limit = 50, signal?: AbortSignal) =>
  apiRequest<{ entries: AuditEntry[] }>(`${V1}/system/audit${qs({ limit })}`, { signal });
export const reconcileAll = (signal?: AbortSignal) => apiRequest<Reconciliation>(`${V1}/system/reconcile`, { signal });
export const backupNow = () => mutate<{ backup: string }>("POST", `${V1}/system/backup`);
