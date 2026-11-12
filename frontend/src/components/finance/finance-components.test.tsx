import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { Bar, Provenance } from "../../types/finance";
import { FreshnessBadge, freshnessLabel } from "./FreshnessBadge";
import { Notice } from "./Notice";
import { PriceChart } from "./PriceChart";

const base: Provenance = {
  mode: "live",
  available: true,
  source: "twelvedata",
  last_known: false,
  saved_at: null,
  delayed: false,
  market_open: true,
  observed_at: "2026-05-01T15:00:00+00:00",
  retrieved_at: "2026-05-01T15:00:05+00:00",
  age_seconds: 12,
  attempts: [],
  notes: [],
};

describe("FreshnessBadge", () => {
  it("says NOT AVAILABLE when there is neither live nor saved data", () => {
    const label = freshnessLabel({ ...base, mode: "unavailable", available: false, source: null });
    expect(label.kind).toBe("unavailable");
    expect(label.text).toBe("NOT AVAILABLE");
  });

  it("labels saved data as last known and shows when it was observed, never as live", () => {
    const label = freshnessLabel({
      ...base,
      mode: "last_known",
      last_known: true,
      saved_at: "2026-05-01T15:30:00+00:00",
    });
    expect(label.kind).toBe("last-known");
    expect(label.text).toContain("LAST KNOWN");
    expect(label.text).toContain("2026");
    expect(label.text).not.toContain("LIVE");
  });

  it("labels retrieved history with its source", () => {
    const label = freshnessLabel({ ...base, mode: "retrieved" });
    expect(label.kind).toBe("retrieved");
    expect(label.text).toContain("twelvedata");
  });

  it("lists every source that was tried in the tooltip", () => {
    const html = renderToStaticMarkup(
      <FreshnessBadge
        provenance={{
          ...base,
          attempts: [
            { source: "twelvedata", outcome: "rate_limited", detail: "limit" },
            { source: "tiingo", outcome: "ok", detail: null },
          ],
        }}
      />,
    );
    expect(html).toContain("twelvedata: rate_limited");
    expect(html).toContain("tiingo: ok");
  });

  it("flags delayed and delay-unknown data", () => {
    expect(freshnessLabel({ ...base, mode: "delayed", delayed: true }).text).toContain("DELAYED");
    const unknown = freshnessLabel({ ...base, mode: "live_delay_unknown", delayed: null });
    expect(unknown.text).toContain("delay unknown");
    expect(unknown.kind).toBe("delayed");
  });

  it("only says LIVE when the provider confirmed it, and shows the age", () => {
    const live = freshnessLabel(base);
    expect(live.kind).toBe("live");
    expect(live.text).toContain("12s old");
  });

  it("notes a closed market and renders nothing without provenance", () => {
    expect(renderToStaticMarkup(<FreshnessBadge provenance={{ ...base, market_open: false }} />)).toContain("market closed");
    expect(renderToStaticMarkup(<FreshnessBadge provenance={null} />)).toBe("");
  });
});

describe("Notice", () => {
  it("announces errors as alerts and other tones as status", () => {
    expect(renderToStaticMarkup(<Notice tone="error">bad</Notice>)).toContain('role="alert"');
    expect(renderToStaticMarkup(<Notice tone="info">ok</Notice>)).toContain('role="status"');
  });
});

function bars(count: number, withVolume = true): Bar[] {
  return Array.from({ length: count }, (_, i) => ({
    start_at: `2026-01-${String(i + 1).padStart(2, "0")}T00:00:00+00:00`,
    end_at: `2026-01-${String(i + 1).padStart(2, "0")}T23:59:00+00:00`,
    open: String(100 + i),
    high: String(102 + i),
    low: String(99 + i),
    close: String(101 + i),
    volume: withVolume ? String(1000 + i) : null,
  }));
}

describe("PriceChart", () => {
  it("renders an accessible chart", () => {
    const html = renderToStaticMarkup(<PriceChart bars={bars(10)} overlays={{}} kind="line" currency="USD" label="TEST price" />);
    expect(html).toContain('role="img"');
    expect(html).toContain("arrow keys");
    expect(html).toContain("chart-line");
  });

  it("draws candles and volume only from supplied data", () => {
    const candles = renderToStaticMarkup(<PriceChart bars={bars(10)} overlays={{}} kind="candles" currency="USD" label="x" />);
    expect(candles).toContain("candle");
    const noVolume = renderToStaticMarkup(<PriceChart bars={bars(10, false)} overlays={{}} kind="line" currency="USD" label="x" />);
    expect(noVolume).not.toContain("volume-bar");
  });

  it("refuses to draw with too little data", () => {
    expect(renderToStaticMarkup(<PriceChart bars={bars(1)} overlays={{}} kind="line" currency="USD" label="x" />)).toContain("not enough");
  });

  it("refuses non-numeric prices instead of drawing garbage", () => {
    const broken = bars(5).map((b, i) => (i === 2 ? { ...b, close: "NaN" } : b));
    expect(renderToStaticMarkup(<PriceChart bars={broken} overlays={{}} kind="line" currency="USD" label="x" />)).toContain("not enough valid");
  });

  it("draws overlays and leaves gaps for missing values", () => {
    const html = renderToStaticMarkup(
      <PriceChart bars={bars(6)} overlays={{ sma20: [null, null, 101, 102, 103, 104] }} kind="line" currency="USD" label="x" />,
    );
    expect(html).toContain("chart-overlay--a");
    expect(html).toContain("SMA 20");
  });
});
