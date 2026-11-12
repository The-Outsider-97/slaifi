/** Shapes returned by the SLAIFI finance API. Money and quantities are decimal strings; rates are fractions. */

/**
 * How a piece of market data was obtained.
 *  live / delayed / live_delay_unknown: a quote retrieved just now (delay known / unknown)
 *  retrieved: history or search results retrieved just now
 *  last_known: every source failed, so this is the last real observation SLAIFI saved
 *  unavailable: nothing live and nothing saved: shown as NOT AVAILABLE
 */
export type DataMode =
  | "live"
  | "delayed"
  | "live_delay_unknown"
  | "retrieved"
  | "last_known"
  | "unavailable"
  | string;

export type SourceAttempt = { source: string; outcome: string; detail: string | null };

export type Asset = {
  symbol: string;
  display_symbol: string;
  asset_class: string;
  exchange: string | null;
  currency: string | null;
};

export type Provenance = {
  mode: DataMode;
  available: boolean;
  source: string | null;
  last_known: boolean;
  /** When SLAIFI saved a last-known observation (null for live data). */
  saved_at: string | null;
  delayed: boolean | null;
  market_open: boolean | null;
  observed_at: string | null;
  retrieved_at: string | null;
  age_seconds: number | null;
  attempts: SourceAttempt[];
  notes: string[];
};

export type Instrument = {
  asset: Asset;
  name: string | null;
  country: string | null;
  instrument_type: string | null;
};

export type SearchResponse = {
  query: string;
  supported: boolean;
  results: Instrument[];
  provenance: Provenance;
};

export type QuoteResponse = {
  asset: Asset;
  /** False when no source has a live or saved price: show NOT AVAILABLE. */
  available: boolean;
  price: string | null;
  currency: string | null;
  change_rate: number | null;
  previous_close: string | null;
  observed_at: string | null;
  source: string | null;
  last_known: boolean;
  provenance: Provenance;
};

export type Bar = {
  start_at: string;
  end_at: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string | null;
};

export type SeriesResponse = {
  asset: Asset;
  interval: string;
  requested_days: number;
  bars: Bar[];
  overlays: Record<string, (number | null)[]>;
  quality: {
    count: number;
    first_at: string | null;
    last_at: string | null;
    duplicates_removed: number;
    reordered: boolean;
    gap_count: number;
    largest_gap_days: number | null;
    complete: boolean;
  };
  notes: string[];
  provenance: Provenance;
};

export type StatsResponse = {
  asset: Asset;
  interval: string;
  observation_count: number;
  start_at: string | null;
  end_at: string | null;
  first_close: number | null;
  last_close: number | null;
  period_return: number | null;
  annualized_volatility: number | null;
  periods_per_year: number | null;
  max_drawdown: number | null;
  current_drawdown: number | null;
  period_high: number | null;
  period_low: number | null;
  average_volume: number | null;
  best_period_return: number | null;
  worst_period_return: number | null;
  sma_20: number | null;
  sma_50: number | null;
  rsi_14: number | null;
  notes: string[];
  provenance: Provenance;
};

export type CompareResponse = {
  interval: string;
  timestamps: string[];
  series: {
    asset: Asset;
    indexed: (number | null)[];
    period_return: number | null;
    annualized_volatility: number | null;
    max_drawdown: number | null;
  }[];
  correlations: Record<string, number | null> | null;
  notes: string[];
  provenance: Provenance;
};

export type MarketMeta = {
  intervals: string[];
  ranges: string[];
  overlays: string[];
  data_mode: DataMode;
  configured: boolean;
  providers: ProviderStatus[];
};

export type WatchlistResponse = {
  items: { asset: Asset; name: string | null; added_at: string; quote: QuoteResponse | null }[];
  provenance: Provenance;
};

export type Safety = {
  available: boolean;
  allowed: boolean;
  risk_level: string | null;
  blockers: string[];
  warnings: string[];
  reviewer: string;
  detail: string | null;
} | null;

export type Explanation = {
  status: string;
  text: string | null;
  agent: string | null;
  validation_status: string | null;
  warnings: string[];
  safety: Safety;
  label: string;
} | null;

export type Signal = {
  name: string;
  value: number | null;
  direction: string;
  weight: number;
  vote: number;
  rationale: string;
};

export type Finding = { code: string; severity: string; message: string; limit: number | null; observed: number | null };

export type RecommendationReport = {
  asset: Asset;
  generated_at: string;
  horizon_days: number;
  strategy_id: string;
  status: "recommendation" | "insufficient_evidence" | string;
  action: string | null;
  signal_score: number | null;
  score_note: string;
  risk_level: string | null;
  signals: Signal[];
  supporting_signals: string[];
  conflicting_signals: string[];
  invalidation_conditions: string[];
  constraint_findings: Finding[];
  insufficient_reasons: string[];
  prediction: {
    horizon_days: number;
    model: { name: string; version: string };
    interval: { lower_return_rate: number; upper_return_rate: number; nominal_coverage: number } | null;
    median_historical_return_rate: number | null;
    input_data_at: string | null;
  } | null;
  prediction_validation: {
    method: string;
    nominal_coverage: number;
    realized_coverage: number | null;
    test_count: number;
    mean_interval_width: number | null;
    passed: boolean;
    note: string;
  } | null;
  expected_downside_rate: number | null;
  observation_count: number;
  last_bar_at: string | null;
  data_mode: string;
  last_known: boolean;
  position_quantity: string | null;
  model_versions: { name: string; version: string }[];
  summary: string;
  notes: string[];
};

export type RecommendationResponse = {
  report: RecommendationReport;
  strategy: { strategy_id: string; name: string };
  provenance: Provenance;
  explanation: Explanation;
  history_notes: string[];
  disclaimer: string;
};

export type BacktestResponse = {
  symbol: string;
  strategy: { strategy_id: string; name: string };
  result: {
    strategy_id: string;
    bar_count: number;
    start_at: string | null;
    end_at: string | null;
    total_return: number | null;
    annualized_return: number | null;
    max_drawdown: number | null;
    exposure_rate: number | null;
    trade_count: number;
    win_rate: number | null;
    benchmark: { label: string; total_return: number | null; annualized_return: number | null; max_drawdown: number | null };
    excess_return: number | null;
    first_half_return: number | null;
    second_half_return: number | null;
    costs: { commission_rate: number | null; slippage_rate: number | null };
    assumptions: string[];
  } | null;
  message: string | null;
  provenance: Provenance;
  disclaimer: string;
};

export type Strategy = {
  strategy_id: string;
  name: string;
  preset: string | null;
  preset_description?: string | null;
  risk_tolerance: string;
  horizon_days: number;
  horizon_bucket: string;
  capital: string | null;
  max_position_weight: number | null;
  max_drawdown_rate: number | null;
  cash_reserve_rate: number | null;
  max_annualized_volatility: number | null;
  max_concentration_hhi: number | null;
  excluded_symbols: string[];
  prohibited_asset_classes: string[];
  allowed_asset_classes: string[];
  preferred_asset_classes: string[];
  trading_frequency: string;
  income_weight: number | null;
  commission_rate: string;
  commission_minimum: string;
  slippage_rate: string;
  reinvest_dividends: boolean;
};

export type StrategiesResponse = {
  active_strategy_id: string;
  strategies: Strategy[];
  presets: Strategy[];
  note: string;
};

export type PortfolioMeta = {
  portfolio_id: string;
  name: string;
  base_currency: string;
  starting_capital: string;
  strategy_id: string | null;
  created_at: string;
  epoch: number;
};

export type PositionRow = {
  asset: Asset;
  quantity: string;
  average_cost: string;
  market_price: string | null;
  market_value: string | null;
  unrealized_pnl: string | null;
  realized_pnl: string;
  weight: number | null;
  price_basis: string;
  stale_price: boolean;
  price_provenance: Provenance | null;
};

export type PortfolioView = {
  portfolio: PortfolioMeta;
  as_of: string;
  currency: string;
  cash_balance: string;
  invested_value: string;
  total_value: string;
  cash_weight: number | null;
  net_contributions: string;
  total_pnl: string;
  simple_return: number | null;
  realized_pnl: string;
  unrealized_pnl: string | null;
  fees_paid: string;
  slippage_cost: string;
  positions: PositionRow[];
  valuation_complete: boolean;
  simulated: true;
  warnings: string[];
};

export type OrderDecision = {
  status: "filled" | "rejected";
  rejections: { code: string; message: string }[];
  warnings: string[];
  trade: { trade_id: string; side: string; quantity: string; unit_price: string; fee: string; occurred_at: string } | null;
  execution: {
    quote_price: string;
    execution_price: string;
    slippage_per_unit: string;
    commission: string;
    gross_amount: string;
    net_cash_effect: string;
    currency: string;
    quote_observed_at: string;
    quote_source: string;
    data_mode: string;
    executed_at: string;
    market_open: boolean | null;
    notes: string[];
  } | null;
  simulated: true;
};

export type OrderOutcome = {
  decision: OrderDecision;
  asset: Asset;
  duplicate: boolean;
  dry_run: boolean;
  strategy_id: string | null;
  portfolio: PortfolioView | null;
};

export type HistoryEntry = { at: string; kind: string; summary: string; detail: Record<string, unknown> };

export type PerformanceResponse = {
  portfolio_id: string;
  point_count: number;
  start_at: string | null;
  end_at: string | null;
  time_weighted_return: number | null;
  annualized_return: number | null;
  max_drawdown: number | null;
  current_drawdown: number | null;
  net_profit: string | null;
  net_contributions: string;
  total_pnl: string;
  simple_return: number | null;
  realized_pnl: string;
  unrealized_pnl: string | null;
  fees_paid: string;
  slippage_cost: string;
  exposure: number | null;
  cash_weight: number | null;
  largest_position_weight: number | null;
  concentration_hhi: number | null;
  equity_curve: { at: string; value: string }[];
  notes: string[];
};

export type Goal = {
  goal_id: string;
  name: string;
  currency: string;
  created_at: string;
  basis: string;
  target_amount: string | null;
  period: string | null;
  target_annual_rate: number | null;
  horizon_years: number | null;
  starting_capital: string | null;
  monthly_contribution: string;
  monthly_withdrawal: string;
  risk_tolerance: string | null;
  max_acceptable_drawdown_rate: number | null;
  portfolio_id: string | null;
  target_value: string | null;
};

export type GoalPlan = {
  kind: string;
  basis_note: string;
  capital: string | null;
  years_used: number;
  required_annual_return_rate: number | null;
  required_monthly_contribution: string | null;
  projected_balance: string | null;
  balance_gap: string | null;
  months_capital_lasts: number | null;
  lasts_beyond_100_years: boolean;
  sustainable_monthly_withdrawal: string | null;
  replanned_from_today: boolean;
};

export type GoalReport = {
  goal_id: string;
  consistent: boolean;
  status: string;
  capital_used: string | null;
  annual_target_amount: string | null;
  required_annual_return_rate: number | null;
  required_capital_at_assumed_rate: string | null;
  assumed_annual_return_rate: number | null;
  scenarios: {
    label: string;
    annual_return_rate: number;
    source: string;
    projected_value: string | null;
    period_profit: string | null;
    shortfall: string | null;
    meets_target: boolean | null;
    stress_loss: string | null;
  }[];
  findings: { code: string; severity: string; message: string }[];
  assumptions: string[];
  progress: {
    basis: string;
    window: string;
    measured_amount: string;
    target_amount: string | null;
    progress_ratio: number | null;
    on_track: boolean | null;
    detail: string;
  } | null;
  plan?: GoalPlan | null;
  disclaimer: string;
};

export type AdvisorChange = {
  index: number;
  field: string;
  old: unknown;
  new: unknown;
  persistence: string;
  description: string;
  hard_limit: boolean;
  loosens_limit: boolean;
};

export type AdvisorResponse = {
  text: string;
  blocked: boolean;
  unrecognised: boolean;
  intents: string[];
  understood: string[];
  safety: Safety;
  changes: AdvisorChange[];
  temporary_changes: AdvisorChange[];
  temporary_analysis: {
    description: string;
    changes: string[];
    new_findings: string[];
    resolved_findings: string[];
    aligned_before: boolean | null;
    aligned_after: boolean | null;
  } | null;
  goals: {
    name: string;
    draft: Record<string, unknown>;
    report: GoalReport | null;
    error: string | null;
  }[];
  orders: {
    draft: { side: string; symbol: string | null; quantity: string | null; notional: string | null; close_position: boolean };
    preview: OrderOutcome | null;
    error: string | null;
  }[];
  contradictions: { description: string; fields: string[] }[];
  warnings: string[];
  explanation: Explanation;
  proposal: { proposal_id: string; created_at: string; expires_at: string; status: string; kind: string } | null;
  requires_confirmation: boolean;
  needs_acknowledgement_of_limits: boolean;
  needs_acknowledgement_of_contradictions: boolean;
  disclaimer: string;
};

export type ConfirmResponse = {
  proposal_id: string;
  applied_changes: string[];
  created_goal_ids: string[];
  orders: OrderOutcome[];
  strategy: Strategy;
};

export type GuidanceResponse = {
  portfolio_id: string;
  strategy: { strategy_id: string; name: string };
  aligned: boolean;
  generated_at: string;
  items: {
    severity: string;
    category: string;
    title: string;
    detail: string;
    suggestion: string | null;
    symbol: string | null;
    quantity: string | null;
    amount: string | null;
  }[];
  goals: {
    goal_id: string;
    name: string;
    status: string;
    consistent: boolean;
    required_annual_return_rate: number | null;
    measured_progress: number | null;
    findings: string[];
  }[];
  holdings: {
    symbol: string;
    action: string | null;
    status: string;
    signal_score: number | null;
    summary: string;
    invalidation_conditions: string[];
  }[];
  metrics: Record<string, number | string | null>;
  data_notes: string[];
  explanation: Explanation;
  disclaimer: string;
};

export type Reconciliation = {
  portfolio_id: string | null;
  checked_at: string;
  consistent: boolean;
  trade_count: number;
  cash_flow_count: number;
  cash_balance: string | null;
  database_integrity: string | null;
  audit_chain_intact: boolean | null;
  issues: { severity: string; code: string; message: string }[];
};

export type SystemStatus = {
  storage_status: string;
  audit_chain_intact: boolean;
  audit_chain_detail: string | null;
  market_providers: { name: string; configured: boolean; state: string }[];
  market_configured: boolean;
  data_mode: string;
  real_money_trading: string;
  paper_trading: {
    allow_closed_market_execution: boolean;
    max_quote_age_seconds: number;
  };
  slai_enabled: boolean;
  client_header_required: boolean;
};

export type AuditEntry = {
  seq: number;
  at: string;
  actor: string;
  action: string;
  subject: string;
  detail: Record<string, unknown>;
  hash: string;
};

export type ProviderState =
  | "ready"
  | "cooling_down"
  | "rejected_credentials"
  | "not_configured"
  | string;

export type ProviderStatus = {
  name: string;
  label: string;
  configured: boolean;
  capabilities: string[];
  intervals: string[];
  state: ProviderState;
  cooldown_until: string | null;
  last_success_at: string | null;
  last_error: string | null;
  last_error_at: string | null;
  calls_last_minute: number;
  calls_today: number;
  free_tier_note: string | null;
};

export type ProvidersResponse = { configured: boolean; providers: ProviderStatus[] };

export type ProviderCheck = {
  name: string;
  configured: boolean;
  ok: boolean;
  detail: string;
  latency_ms: number | null;
};

export type TrackRecord = {
  logged: number;
  pending: number;
  scored: number;
  hits: number;
  hit_rate: number | null;
  interval_low: number | null;
  interval_high: number | null;
  verdict: "insufficient_sample" | "better_than_chance" | "no_clear_edge" | "worse_than_chance";
  minimum_for_verdict: number;
  by_action: { action: string; scored: number; hits: number; mean_forward_return: number | null }[];
  note: string;
  method: string;
};

export type TrackRecordRefresh = {
  refresh: { evaluated: number; waiting: number; unchecked_symbols: string[]; deferred_symbols: number; notes: string[] };
  track_record: TrackRecord;
};

export type AdaptationProposal = {
  code: string;
  kind: "tighten" | "align" | "observation";
  title: string;
  rationale: string;
  evidence: string[];
  change: Record<string, unknown> | null;
};

export type AdaptationResponse = {
  strategy: { strategy_id: string; name: string };
  portfolio_id: string | null;
  proposals: AdaptationProposal[];
  notes: string[];
  track_record: TrackRecord;
  explanation: Explanation | null;
};

export type GoalReview = { report: GoalReport; explanation: Explanation };
