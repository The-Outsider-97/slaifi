export type MarketQuote = {
  symbol: string;
  asset_class: string;
  price: string;
  currency: string;
  change_percent: string | null;
  observed_at: string;
  source: string;
};

export type MarketOverview = {
  generated_at: string;
  quotes: MarketQuote[];
  data_mode: string;
};

export type SlaiRuntimeStatusValue = "available" | "degraded" | "unavailable" | "disabled";

export type SlaiRuntimeStatus = {
  status: SlaiRuntimeStatusValue;
  interpretation: string | null;
  agent: string | null;
  agent_version: string | null;
  correlation_id: string | null;
  request_id: string | null;
  warnings: string[];
  reasoning_strategy?: string | null;
  confidence?: number | null;
  outcome?: string | null;
  degraded?: boolean;
  validation_status?: string | null;
};

export type OHLCVBarInput = {
  start_at: string;
  end_at: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type MarketAnalysisRequest = {
  asset: {
    symbol: string;
    asset_class: string;
    currency?: string;
  };
  bars: OHLCVBarInput[];
  periods_per_year: number;
  moving_average_period: number;
  momentum_period: number;
  rsi_period: number;
  atr_period: number;
  reasoning_objective: string;
};

export type MarketAnalysisResponse = {
  symbol: string;
  observation_count: number;
  latest_close: number;
  simple_return: number | null;
  rolling_volatility: number | null;
  maximum_drawdown: number | null;
  technical: {
    sma: number | null;
    ema: number | null;
    momentum: number | null;
    rsi: number | null;
    macd: number | null;
    macd_signal: number | null;
    atr: number | null;
  };
  features: Record<string, Array<number | null>>;
  reasoning: SlaiRuntimeStatus | null;
};
