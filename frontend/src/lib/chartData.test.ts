import { describe, expect, it } from "vitest";

import {
  MAX_DAYS,
  alignSeries,
  downsampleIndices,
  indexAtFraction,
  isChartRange,
  niceTicks,
  normalizeSymbols,
  periodStats,
  rangeDays,
  rebasePercent,
  toPoints,
  type Point,
} from "./chartData";
import type { Bar } from "../types/finance";

const bar = (day: number, close: string | null): Bar => ({
  start_at: new Date(Date.UTC(2026, 0, day)).toISOString(),
  end_at: new Date(Date.UTC(2026, 0, day + 1)).toISOString(),
  open: "1",
  high: "1",
  low: "1",
  close: close as string,
  volume: null,
});

const pts = (closes: [number, number][]): Point[] =>
  closes.map(([day, value]) => ({ t: Date.UTC(2026, 0, day), value, at: new Date(Date.UTC(2026, 0, day)).toISOString() }));

describe("ranges", () => {
  it("covers one week to five years and never more", () => {
    expect(rangeDays("1W")).toBe(7);
    expect(rangeDays("5Y")).toBe(MAX_DAYS);
    expect(MAX_DAYS).toBeLessThanOrEqual(1830);
    expect(rangeDays("2Y")).toBeGreaterThan(rangeDays("1Y"));
  });

  it("runs year-to-date from 1 January", () => {
    expect(rangeDays("YTD", new Date(Date.UTC(2026, 2, 1)))).toBe(31 + 28 + 1); // 1 Jan to 1 Mar is 59 days, counted inclusively
    expect(rangeDays("YTD", new Date(Date.UTC(2026, 0, 1)))).toBe(7); // never fewer than a week
  });

  it("recognises only real ranges", () => {
    expect(isChartRange("5Y")).toBe(true);
    expect(isChartRange("10Y")).toBe(false);
    expect(isChartRange(5)).toBe(false);
  });
});

describe("toPoints", () => {
  it("skips a bar with no usable close instead of inventing one", () => {
    const out = toPoints([bar(1, "10"), bar(2, "not-a-number"), bar(3, null), bar(4, ""), bar(5, "12")]);
    expect(out.map((p) => p.value)).toEqual([10, 12]); // a missing close is never drawn as a price of 0
  });

  it("returns the points in date order", () => {
    expect(toPoints([bar(3, "3"), bar(1, "1"), bar(2, "2")]).map((p) => p.value)).toEqual([1, 2, 3]);
  });
});

describe("comparison", () => {
  it("keeps only the days every series has, never filling a gap", () => {
    const a = pts([[1, 10], [2, 11], [3, 12], [4, 13]]);
    const b = pts([[2, 100], [4, 130]]);
    const out = alignSeries([a, b]);
    expect(out.closes[0]).toEqual([11, 13]);
    expect(out.closes[1]).toEqual([100, 130]);
    expect(out.times).toHaveLength(2);
  });

  it("is empty when nothing is shared", () => {
    expect(alignSeries([pts([[1, 1]]), pts([[2, 2]])]).times).toEqual([]);
    expect(alignSeries([]).times).toEqual([]);
  });

  it("rebases to percentage change from the first value", () => {
    expect(rebasePercent([100, 110, 90])).toEqual([0, 10, -10]);
    expect(rebasePercent([0, 5]).every(Number.isNaN)).toBe(true);
  });
});

describe("downsampleIndices", () => {
  it("returns everything when it already fits", () => {
    expect(downsampleIndices([1, 2, 3], 10)).toEqual([0, 1, 2]);
  });

  it("keeps the ends and the extremes of a long series", () => {
    const values = Array.from({ length: 2000 }, (_, i) => Math.sin(i / 40));
    values[1234] = 5; // a spike
    values[777] = -5; // a dip
    const keep = downsampleIndices(values, 300);
    expect(keep.length).toBeLessThanOrEqual(300);
    expect(keep[0]).toBe(0);
    expect(keep[keep.length - 1]).toBe(1999);
    expect(keep).toContain(1234);
    expect(keep).toContain(777);
    expect([...keep].sort((a, b) => a - b)).toEqual(keep);
  });
});

describe("readout helpers", () => {
  it("maps a pointer fraction to the nearest point", () => {
    expect(indexAtFraction(0, 100)).toBe(0);
    expect(indexAtFraction(1, 100)).toBe(99);
    expect(indexAtFraction(0.5, 101)).toBe(50);
    expect(indexAtFraction(-3, 10)).toBe(0);
    expect(indexAtFraction(7, 10)).toBe(9);
    expect(indexAtFraction(Number.NaN, 10)).toBe(0);
    expect(indexAtFraction(0.5, 0)).toBe(-1);
  });

  it("summarises a period", () => {
    const s = periodStats([100, 120, 90, 110]);
    expect(s).toEqual({ first: 100, last: 110, change: 10, changePercent: 10, high: 120, low: 90 });
    expect(periodStats([])).toBeNull();
    expect(periodStats([0, 5])?.changePercent).toBeNull();
  });

  it("chooses round axis ticks", () => {
    expect(niceTicks(0, 100, 4)).toEqual([0, 50, 100]);
    const ticks = niceTicks(605, 806, 4);
    expect(ticks.every((t) => t >= 605 && t <= 806)).toBe(true);
    expect(niceTicks(5, 5)).toEqual([5]);
  });
});

describe("normalizeSymbols", () => {
  it("cleans, de-duplicates and limits what was typed or stored", () => {
    expect(normalizeSymbols([" spy ", "SPY", "qqq", 5, null, "bad symbol!", "^VIX", "DIA", "IWM"], 3)).toEqual(["SPY", "QQQ", "^VIX"]);
  });
});
