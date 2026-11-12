import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearSeriesCache, loadSeries } from "./seriesCache";

const series = (bars: number, mode = "retrieved") => ({
  asset: { symbol: "SPY", display_symbol: "SPY", asset_class: "etf", exchange: null, currency: "USD" },
  interval: "1day",
  requested_days: 93,
  bars: Array.from({ length: bars }, (_, i) => ({ start_at: `2026-01-${String(i + 1).padStart(2, "0")}T00:00:00Z`, end_at: "", open: "1", high: "1", low: "1", close: "1", volume: null })),
  overlays: {},
  quality: {},
  notes: [],
  provenance: { mode, available: mode !== "unavailable", source: "test", last_known: false, saved_at: null, delayed: null, market_open: null, observed_at: null, retrieved_at: null, age_seconds: null, attempts: [], notes: [] },
});

let calls: string[] = [];

function mockFetch(answer: () => unknown) {
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      calls.push(String(url));
      return new Response(JSON.stringify(answer()), { status: 200, headers: { "Content-Type": "application/json" } });
    }),
  );
}

describe("loadSeries", () => {
  beforeEach(() => clearSeriesCache());
  afterEach(() => vi.unstubAllGlobals());

  it("makes one request for the same symbol and range, even when asked at the same moment", async () => {
    mockFetch(() => series(3));
    const [a, b] = await Promise.all([loadSeries("spy", 93), loadSeries("SPY", 93)]);
    expect(a).toBe(b);
    expect(calls).toHaveLength(1);
    expect(calls[0]).toContain("days=93");
    await loadSeries("SPY", 93);
    expect(calls).toHaveLength(1); // remembered
  });

  it("asks again for a different range or other overlays", async () => {
    mockFetch(() => series(3));
    await loadSeries("SPY", 93);
    await loadSeries("SPY", 366);
    await loadSeries("SPY", 93, ["sma20"]);
    expect(calls).toHaveLength(3);
    expect(calls[2]).toContain("overlays=sma20");
  });

  it("never remembers an empty or unavailable answer", async () => {
    mockFetch(() => series(0));
    await loadSeries("QQQ", 93);
    await loadSeries("QQQ", 93);
    expect(calls).toHaveLength(2);
    mockFetch(() => series(3, "unavailable"));
    await loadSeries("DIA", 93);
    await loadSeries("DIA", 93);
    expect(calls).toHaveLength(2);
  });

  it("forgets an answer after five minutes", async () => {
    mockFetch(() => series(3));
    let now = 1_000;
    await loadSeries("IWM", 93, [], () => now);
    now += 4 * 60_000;
    await loadSeries("IWM", 93, [], () => now);
    expect(calls).toHaveLength(1);
    now += 2 * 60_000;
    await loadSeries("IWM", 93, [], () => now);
    expect(calls).toHaveLength(2);
  });
});
