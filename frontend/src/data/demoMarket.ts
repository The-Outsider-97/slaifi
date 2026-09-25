import type { MarketAnalysisRequest } from "../types/market";

export type MarketRange = "1W" | "1M" | "3M" | "1Y";

type RangeSeries = {
  values: readonly number[];
  labels: readonly string[];
  changePercent: number;
  periodLabel: string;
};

const THREE_MONTH_VALUES = [
  5350, 5324, 5380, 5410, 5484, 5460, 5495, 5472, 5504, 5582,
  5610, 5558, 5521, 5552, 5502, 5545, 5612, 5598, 5640, 5628,
  5570, 5609, 5585, 5651, 5712, 5742, 5701, 5725, 5682, 5689,
  5758, 5790, 5768, 5708, 5699, 5744, 5770, 5748, 5799, 5850,
  5864, 5821, 5844, 5782.76,
] as const;

export const ILLUSTRATIVE_RANGES: Record<MarketRange, RangeSeries> = {
  "1W": {
    values: [5710, 5730, 5706, 5750, 5772, 5760, 5782.76],
    labels: ["MON", "WED", "FRI"],
    changePercent: 1.27,
    periodLabel: "past week",
  },
  "1M": {
    values: [5610, 5634, 5598, 5660, 5689, 5670, 5715, 5698, 5740, 5766, 5744, 5782.76],
    labels: ["SEP 01", "SEP 15", "SEP 30"],
    changePercent: 3.08,
    periodLabel: "past month",
  },
  "3M": {
    values: THREE_MONTH_VALUES,
    labels: ["JUL 01", "AUG 01", "SEP 01", "SEP 30"],
    changePercent: 6.24,
    periodLabel: "past 3 months",
  },
  "1Y": {
    values: [4720, 4810, 4788, 4904, 5020, 5142, 5204, 5355, 5428, 5512, 5688, 5782.76],
    labels: ["OCT", "JAN", "APR", "JUL", "SEP"],
    changePercent: 18.61,
    periodLabel: "past year",
  },
};

export const SUMMARY_FALLBACKS = [
  { key: "SPY", name: "S&P 500", value: 5782.76, changePercent: 0.82, sparkline: [4, 6, 5, 9, 8, 11, 9, 13, 14] },
  { key: "QQQ", name: "NASDAQ", value: 18239.92, changePercent: 1.24, sparkline: [5, 7, 6, 10, 9, 12, 10, 13, 14] },
  { key: "DIA", name: "DOW JONES", value: 42313.0, changePercent: 0.45, sparkline: [5, 8, 7, 11, 9, 12, 11, 14, 13] },
  { key: "VIX", name: "VIX", value: 16.52, changePercent: -2.31, sparkline: [14, 12, 13, 10, 11, 8, 9, 7, 8] },
] as const;

export const MARKET_WATCH_ROWS = [
  { symbol: "AAPL", name: "Apple Inc.", price: 227.82, changePercent: 1.12, signal: "Hold" },
  { symbol: "NVDA", name: "NVIDIA Corporation", price: 121.40, changePercent: 2.18, signal: "Review risk" },
  { symbol: "MSFT", name: "Microsoft Corporation", price: 428.02, changePercent: -0.36, signal: "Hold" },
  { symbol: "VOO", name: "Vanguard S&P 500 ETF", price: 531.68, changePercent: 0.81, signal: "DCA" },
] as const;

export function buildIllustrativeMarketAnalysisRequest(): MarketAnalysisRequest {
  const start = Date.UTC(2026, 6, 1);
  const day = 24 * 60 * 60 * 1000;
  const bars = THREE_MONTH_VALUES.map((close, index) => {
    const previous = index === 0 ? close * 0.997 : THREE_MONTH_VALUES[index - 1];
    const open = Number(previous.toFixed(2));
    const closeValue = Number(close.toFixed(2));
    const high = Number((Math.max(open, closeValue) * 1.004).toFixed(2));
    const low = Number((Math.min(open, closeValue) * 0.996).toFixed(2));
    return {
      start_at: new Date(start + index * day).toISOString(),
      end_at: new Date(start + (index + 1) * day).toISOString(),
      open,
      high,
      low,
      close: closeValue,
      volume: 1_000_000 + index * 12_500,
    };
  });

  return {
    asset: { symbol: "SPX", asset_class: "index", currency: "USD" },
    bars,
    periods_per_year: 252,
    moving_average_period: 10,
    momentum_period: 5,
    rsi_period: 7,
    atr_period: 7,
    reasoning_objective: "Explain the big picture from this illustrative S&P 500 three-month series. Use the authoritative SLAIFI calculations and structure the interpretation around market context, observed evidence, risk, goal relevance, conflicting signals, uncertainty, and what would change the view. Do not create a trade instruction, guaranteed return, or replacement calculation.",
  };
}
