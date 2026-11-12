/** Pure helpers behind the interactive market chart. No fetching, no drawing, no invented values. */

import type { Bar } from "../types/finance";

export type ChartRange = "1W" | "1M" | "3M" | "6M" | "YTD" | "1Y" | "2Y" | "5Y";

export const CHART_RANGES: ChartRange[] = ["1W", "1M", "3M", "6M", "YTD", "1Y", "2Y", "5Y"];

/** Hard ceiling of the product: five years of history. */
export const MAX_DAYS = 1830;

const FIXED_DAYS: Record<Exclude<ChartRange, "YTD">, number> = {
  "1W": 7,
  "1M": 31,
  "3M": 93,
  "6M": 186,
  "1Y": 366,
  "2Y": 731,
  "5Y": MAX_DAYS,
};

export function isChartRange(value: unknown): value is ChartRange {
  return typeof value === "string" && (CHART_RANGES as string[]).includes(value);
}

/** Calendar days to request for a range. "YTD" runs from 1 January of the current year. */
export function rangeDays(range: ChartRange, now: Date = new Date()): number {
  if (range !== "YTD") return FIXED_DAYS[range];
  const startOfYear = Date.UTC(now.getUTCFullYear(), 0, 1);
  const days = Math.ceil((now.getTime() - startOfYear) / 86_400_000) + 1;
  return Math.min(MAX_DAYS, Math.max(7, days));
}

export type Point = { t: number; value: number; at: string };

/** Closing prices as points. A bar without a finite close is skipped, never replaced by a guess. */
export function toPoints(bars: readonly Bar[]): Point[] {
  const points: Point[] = [];
  for (const bar of bars) {
    // Number(null) and Number("") are 0, which would draw a missing close as a price of zero.
    const raw = bar.close as string | number | null | undefined;
    if (raw === null || raw === undefined || String(raw).trim() === "") continue;
    const value = Number(raw);
    const t = Date.parse(bar.start_at);
    if (Number.isFinite(value) && Number.isFinite(t)) points.push({ t, value, at: bar.start_at });
  }
  points.sort((a, b) => a.t - b.t);
  return points;
}

const DAY_MS = 86_400_000;
const dayKey = (t: number) => Math.floor(t / DAY_MS);

export type Aligned = {
  /** One entry per day on which every series has a real close. */
  times: number[];
  stamps: string[];
  /** series[i][j] is the close of series i on times[j]. */
  closes: number[][];
};

/** Keep only the days all series share, so a comparison never fills a gap with a made-up value. */
export function alignSeries(series: readonly (readonly Point[])[]): Aligned {
  if (series.length === 0) return { times: [], stamps: [], closes: [] };
  const maps = series.map((points) => new Map(points.map((p) => [dayKey(p.t), p])));
  const first = series[0] ?? [];
  const times: number[] = [];
  const stamps: string[] = [];
  const closes: number[][] = series.map(() => []);
  for (const point of first) {
    const key = dayKey(point.t);
    const row = maps.map((m) => m.get(key));
    if (row.some((p) => p === undefined)) continue;
    times.push(point.t);
    stamps.push(point.at);
    row.forEach((p, i) => closes[i]?.push((p as Point).value));
  }
  return { times, stamps, closes };
}

/** Percentage change of every value from the first one ("rebased to 0 %"). */
export function rebasePercent(values: readonly number[]): number[] {
  const base = values[0];
  if (base === undefined || base === 0) return values.map(() => Number.NaN);
  return values.map((v) => ((v - base) / base) * 100);
}

/**
 * Reduce to at most ``max`` points for drawing, keeping each bucket's highest and lowest value so
 * spikes survive. Returns indices into the original array (first and last are always kept).
 */
export function downsampleIndices(values: readonly number[], max: number): number[] {
  const n = values.length;
  if (max < 4 || n <= max) return Array.from({ length: n }, (_, i) => i);
  const buckets = Math.floor((max - 2) / 2);
  const size = (n - 2) / buckets;
  const keep = new Set<number>([0, n - 1]);
  for (let b = 0; b < buckets; b++) {
    const start = 1 + Math.floor(b * size);
    const end = Math.min(n - 1, 1 + Math.floor((b + 1) * size));
    let lo = start;
    let hi = start;
    for (let i = start; i < end; i++) {
      if ((values[i] as number) < (values[lo] as number)) lo = i;
      if ((values[i] as number) > (values[hi] as number)) hi = i;
    }
    keep.add(lo);
    keep.add(hi);
  }
  return [...keep].sort((a, b) => a - b);
}

/** Index of the entry nearest to ``fraction`` (0..1) of the way along ``count`` entries. */
export function indexAtFraction(fraction: number, count: number): number {
  if (count <= 0) return -1;
  const clamped = Math.min(1, Math.max(0, Number.isFinite(fraction) ? fraction : 0));
  return Math.round(clamped * (count - 1));
}

export type PeriodStats = {
  first: number;
  last: number;
  change: number;
  changePercent: number | null;
  high: number;
  low: number;
};

export function periodStats(values: readonly number[]): PeriodStats | null {
  if (values.length === 0) return null;
  const first = values[0] as number;
  const last = values[values.length - 1] as number;
  let high = first;
  let low = first;
  for (const v of values) {
    if (v > high) high = v;
    if (v < low) low = v;
  }
  return { first, last, change: last - first, changePercent: first === 0 ? null : ((last - first) / first) * 100, high, low };
}

/** "Nice" tick values between min and max (about ``count`` of them). */
export function niceTicks(min: number, max: number, count = 4): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [];
  if (min === max) return [min];
  const rough = (max - min) / Math.max(1, count);
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const residual = rough / magnitude;
  const step = (residual >= 5 ? 10 : residual >= 2 ? 5 : residual >= 1 ? 2 : 1) * magnitude;
  const ticks: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + step * 1e-9; v += step) {
    ticks.push(Number(v.toPrecision(12)));
  }
  return ticks;
}

/** A readable axis label for a date, with the year once the span is long enough to need it. */
export function axisDate(t: number, spanDays: number): string {
  const date = new Date(t);
  return new Intl.DateTimeFormat("en-US", spanDays > 300 ? { month: "short", year: "2-digit" } : { month: "short", day: "2-digit" }).format(date);
}

/** Symbols as people type them: trimmed, upper case, no duplicates, at most ``limit`` kept. */
export function normalizeSymbols(values: readonly unknown[], limit: number): string[] {
  const seen = new Set<string>();
  for (const raw of values) {
    if (typeof raw !== "string") continue;
    const symbol = raw.trim().toUpperCase();
    if (symbol && symbol.length <= 24 && /^[A-Z0-9.:^/-]+$/.test(symbol) && !seen.has(symbol)) {
      seen.add(symbol);
      if (seen.size >= limit) break;
    }
  }
  return [...seen];
}
