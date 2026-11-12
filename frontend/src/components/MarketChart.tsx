import { useCallback, useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

import {
  CHART_RANGES,
  alignSeries,
  axisDate,
  downsampleIndices,
  indexAtFraction,
  niceTicks,
  periodStats,
  rangeDays,
  rebasePercent,
  toPoints,
  type ChartRange,
  type Point,
} from "../lib/chartData";
import { dateTime, money } from "../lib/format";
import { loadSeries } from "../lib/seriesCache";
import { errorText } from "../services/api";
import type { SeriesResponse } from "../types/finance";
import type { MarketHistory } from "../types/market";
import { FreshnessBadge } from "./finance/FreshnessBadge";
import { SymbolPicker } from "./SymbolPicker";

export const MAX_COMPARED = 3;
const SERIES_COLORS = ["var(--accent)", "#7aa7d9", "#b58ad9"];
const HEIGHT = 280;
const PAD_RIGHT = 58;
const PAD_BOTTOM = 22;
const MAX_DRAWN = 700;
const MIN_ZOOM_POINTS = 5;

type Suggestion = { symbol: string; label?: string };

type Props = {
  symbols: string[];
  range: ChartRange;
  onSymbols: (symbols: string[]) => void;
  onRange: (range: ChartRange) => void;
  /** Quick picks: the user's own assets first. */
  suggestions: Suggestion[];
  /** The first symbol's history, for the SLAI reading next to the chart. */
  onPrimaryHistory?: (history: MarketHistory | null) => void;
  /** True while the page is still working out what to show first. */
  waiting?: boolean;
};

type Loaded = { series?: SeriesResponse; error?: string };

function useWidth(ref: React.RefObject<HTMLElement | null>, fallback = 760): number {
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const element = ref.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      const next = Math.round(entry?.contentRect.width ?? 0);
      if (next > 120) setWidth(next);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);
  return width;
}

function axisNumber(value: number, percentMode: boolean): string {
  if (percentMode) return `${value > 0 ? "+" : ""}${value.toFixed(Math.abs(value) < 10 ? 1 : 0)}%`;
  return Math.abs(value) >= 1000 ? Math.round(value).toLocaleString("en-US") : value.toFixed(2);
}

function toHistory(series: SeriesResponse): MarketHistory {
  const p = series.provenance;
  return {
    symbol: series.asset.symbol,
    asset_class: series.asset.asset_class,
    interval: series.interval,
    generated_at: p.retrieved_at ?? new Date().toISOString(),
    data_mode: p.last_known ? "last_known" : "retrieved",
    source: p.source,
    last_known: p.last_known,
    saved_at: p.saved_at,
    bars: series.bars.map((bar) => ({
      start_at: bar.start_at,
      end_at: bar.end_at,
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
      volume: bar.volume ?? "0",
    })),
  };
}

function pathOf(indices: number[], x: (i: number) => number, y: (v: number) => number, values: number[]): string {
  let d = "";
  let pen = false;
  for (const i of indices) {
    const v = values[i];
    if (v === undefined || !Number.isFinite(v)) {
      pen = false;
      continue;
    }
    d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
    pen = true;
  }
  return d;
}

/**
 * Interactive price chart for the Market overview.
 *
 * Choose up to three instruments (search, or tap one of your own), a range from one week to five
 * years, and read exact values by hovering, touching or using the arrow keys. Drag across the chart
 * to zoom in; double-click or "Reset zoom" returns to the whole range. With more than one
 * instrument the lines are shown as percentage change over the same days. Only days on which every
 * chosen instrument has a real close are drawn.
 */
export function MarketChart({ symbols, range, onSymbols, onRange, suggestions, onPrimaryHistory, waiting = false }: Props) {
  const titleId = useId();
  const fillId = useId().replace(/:/g, "");
  const frame = useRef<HTMLDivElement>(null);
  const width = useWidth(frame);

  const [loaded, setLoaded] = useState<Record<string, Loaded>>({});
  const [loading, setLoading] = useState(true);
  const [showSma, setShowSma] = useState({ sma20: false, sma50: false });
  const [percentView, setPercentView] = useState(false);
  const [zoom, setZoom] = useState<[number, number] | null>(null);
  const [cursor, setCursor] = useState<number | null>(null);
  const [drag, setDrag] = useState<{ from: number; to: number } | null>(null);

  const key = symbols.join(",");
  const single = symbols.length === 1;
  const overlayNames = useMemo(
    () => (single ? (["sma20", "sma50"] as const).filter((name) => showSma[name]) : []),
    [single, showSma],
  );
  const overlayKey = overlayNames.join(",");

  // ---------------------------------------------------------------- data
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setZoom(null);
    setCursor(null);
    const days = rangeDays(range);
    Promise.all(
      symbols.map(async (symbol): Promise<[string, Loaded]> => {
        try {
          const series = await loadSeries(symbol, days, symbols.length === 1 ? overlayNames : []);
          if (series.bars.length < 2) return [symbol, { error: "NOT AVAILABLE · no live or saved history for this instrument." }];
          return [symbol, { series }];
        } catch (failure) {
          return [symbol, { error: errorText(failure) || "The request failed." }];
        }
      }),
    ).then((entries) => {
      if (cancelled) return;
      setLoaded(Object.fromEntries(entries));
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keyed on the joined symbols and overlay names
  }, [key, range, overlayKey]);

  const primary = symbols[0] ? loaded[symbols[0]]?.series : undefined;
  useEffect(() => {
    onPrimaryHistory?.(primary ? toHistory(primary) : null);
  }, [primary, onPrimaryHistory]);

  // ---------------------------------------------------------------- model
  const model = useMemo(() => {
    const usable = symbols.filter((s) => loaded[s]?.series);
    if (usable.length === 0) return null;
    const perSymbol: Point[][] = usable.map((s) => toPoints((loaded[s]?.series as SeriesResponse).bars));
    let times: number[];
    let stamps: string[];
    let closes: number[][];
    if (usable.length === 1) {
      const only = perSymbol[0] as Point[];
      times = only.map((p) => p.t);
      stamps = only.map((p) => p.at);
      closes = [only.map((p) => p.value)];
    } else {
      ({ times, stamps, closes } = alignSeries(perSymbol));
    }
    if (times.length < 2) return { usable, times, stamps, closes, overlays: {} as Record<string, number[]>, sparse: true };
    const overlays: Record<string, number[]> = {};
    if (usable.length === 1) {
      const series = loaded[usable[0] as string]?.series as SeriesResponse;
      if (series.bars.length === times.length) {
        for (const name of overlayNames) {
          const raw = series.overlays[name];
          if (raw) overlays[name] = raw.map((v) => (v === null ? Number.NaN : v));
        }
      }
    }
    return { usable, times, stamps, closes, overlays, sparse: false };
  }, [symbols, loaded, overlayNames]);

  const percentMode = symbols.length > 1 || percentView;

  const view = useMemo(() => {
    if (!model || model.sparse) return null;
    const total = model.times.length;
    const [lo, hi] = zoom ?? [0, total - 1];
    const slice = (values: number[]) => values.slice(lo, hi + 1);
    const base = model.closes.map(slice);
    const shown = percentMode ? base.map(rebasePercent) : base;
    const shownOverlays: Record<string, number[]> = {};
    for (const [name, values] of Object.entries(model.overlays)) {
      const raw = slice(values);
      if (!percentMode) shownOverlays[name] = raw;
    }
    let min = Number.POSITIVE_INFINITY;
    let max = Number.NEGATIVE_INFINITY;
    for (const values of [...shown, ...Object.values(shownOverlays)]) {
      for (const v of values) {
        if (Number.isFinite(v)) {
          if (v < min) min = v;
          if (v > max) max = v;
        }
      }
    }
    if (percentMode) {
      min = Math.min(min, 0);
      max = Math.max(max, 0);
    }
    const span = max - min || Math.max(1, Math.abs(max) * 0.01);
    min -= span * 0.06;
    max += span * 0.06;
    const times = model.times.slice(lo, hi + 1);
    const stamps = model.stamps.slice(lo, hi + 1);
    return { lo, hi, base, shown, shownOverlays, min, max, times, stamps, count: times.length };
  }, [model, zoom, percentMode]);

  // ---------------------------------------------------------------- geometry
  const plotW = Math.max(120, width - PAD_RIGHT);
  const plotH = HEIGHT - PAD_BOTTOM;
  const geometry = useMemo(() => {
    if (!view) return null;
    const x = (i: number) => (view.count <= 1 ? 0 : (i / (view.count - 1)) * plotW);
    const y = (v: number) => plotH - ((v - view.min) / (view.max - view.min)) * plotH;
    const paths = view.shown.map((values) => pathOf(downsampleIndices(values, MAX_DRAWN), x, y, values));
    const overlayPaths = Object.entries(view.shownOverlays).map(([name, values]) => ({
      name,
      d: pathOf(downsampleIndices(values, MAX_DRAWN), x, y, values),
    }));
    const first = view.shown[0] ?? [];
    const indices = downsampleIndices(first, MAX_DRAWN);
    const area =
      view.shown.length === 1 && indices.length > 1
        ? `${pathOf(indices, x, y, first)}L${x(indices[indices.length - 1] as number).toFixed(1)},${plotH}L${x(indices[0] as number).toFixed(1)},${plotH}Z`
        : "";
    const yTicks = niceTicks(view.min, view.max, 4);
    const spanDays = view.count > 1 ? ((view.times[view.count - 1] as number) - (view.times[0] as number)) / 86_400_000 : 0;
    const tickCount = Math.min(5, view.count);
    const xTicks = Array.from({ length: tickCount }, (_, n) => {
      const i = tickCount === 1 ? 0 : Math.round((n / (tickCount - 1)) * (view.count - 1));
      return { i, label: axisDate(view.times[i] as number, spanDays) };
    });
    return { x, y, paths, overlayPaths, area, yTicks, xTicks };
  }, [view, plotW, plotH]);

  // ---------------------------------------------------------------- pointer + keyboard
  const indexFromEvent = useCallback(
    (event: PointerEvent<SVGSVGElement>): number => {
      if (!view) return -1;
      const rect = event.currentTarget.getBoundingClientRect();
      return indexAtFraction((event.clientX - rect.left) / Math.max(1, plotW * (rect.width / width)), view.count);
    },
    [view, plotW, width],
  );

  const onPointerMove = (event: PointerEvent<SVGSVGElement>) => {
    const i = indexFromEvent(event);
    if (i < 0) return;
    setCursor(i);
    if (drag) setDrag({ from: drag.from, to: i });
  };
  const onPointerDown = (event: PointerEvent<SVGSVGElement>) => {
    const i = indexFromEvent(event);
    if (i < 0) return;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    setDrag({ from: i, to: i });
  };
  const onPointerUp = () => {
    if (!drag || !view) return setDrag(null);
    const a = Math.min(drag.from, drag.to);
    const b = Math.max(drag.from, drag.to);
    setDrag(null);
    if (b - a + 1 >= MIN_ZOOM_POINTS) {
      setZoom([view.lo + a, view.lo + b]);
      setCursor(null);
    }
  };
  const onKey = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!view) return;
    const last = view.count - 1;
    const at = cursor ?? last;
    if (event.key === "ArrowLeft") setCursor(Math.max(0, at - 1));
    else if (event.key === "ArrowRight") setCursor(Math.min(last, at + 1));
    else if (event.key === "Home") setCursor(0);
    else if (event.key === "End") setCursor(last);
    else if (event.key === "Escape") {
      setCursor(null);
      setZoom(null);
      return;
    } else return;
    event.preventDefault();
  };

  // ---------------------------------------------------------------- readout
  const currency = (symbol: string | undefined) => (symbol ? loaded[symbol]?.series?.asset.currency ?? "USD" : "USD");
  const at = view ? (cursor !== null && cursor < view.count ? cursor : null) : null;
  const stats = view ? view.base.map((values) => periodStats(values)) : [];
  const usable = model?.usable ?? [];
  const errors = symbols.filter((s) => loaded[s]?.error && !loaded[s]?.series);

  const readoutText = (i: number): string => {
    if (!view) return "";
    const when = new Intl.DateTimeFormat("en-US", { weekday: "short", year: "numeric", month: "short", day: "2-digit" }).format(new Date(view.times[i] as number));
    const parts = usable.map((symbol, n) => {
      const price = view.base[n]?.[i];
      const pct = rebasePercent(view.base[n] ?? [])[i];
      return percentMode
        ? `${symbol} ${Number.isFinite(pct) ? `${(pct as number) > 0 ? "+" : ""}${(pct as number).toFixed(2)}%` : "—"} (${money(price, currency(symbol))})`
        : `${symbol} ${money(price, currency(symbol))}${Number.isFinite(pct) ? ` (${(pct as number) > 0 ? "+" : ""}${(pct as number).toFixed(2)}% since start of view)` : ""}`;
    });
    return `${when}: ${parts.join(" · ")}`;
  };

  const addSymbol = (symbol: string) => {
    if (symbols.length >= MAX_COMPARED) return;
    onSymbols([...symbols, symbol].filter((s, i, all) => all.indexOf(s) === i));
  };
  const removeSymbol = (symbol: string) => {
    const next = symbols.filter((s) => s !== symbol);
    if (next.length > 0) onSymbols(next);
  };
  const choose = (symbol: string) => onSymbols([symbol]);

  const primaryStats = stats[0] ?? null;
  const primaryProvenance = primary?.provenance ?? null;

  return (
    <section className="panel performance-panel market-chart" aria-labelledby={titleId}>
      <div className="panel-heading panel-heading--chart">
        <div>
          <span className="section-kicker">MARKET PERFORMANCE</span>
          <h2 id={titleId}>{symbols.join(" vs ") || "Market history"}</h2>
        </div>
        <div className="range-tabs" aria-label="Chart range" role="group">
          {CHART_RANGES.map((item) => (
            <button
              key={item}
              type="button"
              className={item === range ? "range-tab range-tab--active" : "range-tab"}
              aria-pressed={item === range}
              onClick={() => onRange(item)}
            >
              {item}
            </button>
          ))}
        </div>
      </div>

      <div className="chart-controls">
        <ul className="chip-row" aria-label="Instruments on the chart">
          {symbols.map((symbol, n) => (
            <li key={symbol} className="chip chip--series" style={{ borderColor: SERIES_COLORS[n] }}>
              <span className="chip__dot" style={{ background: SERIES_COLORS[n] }} aria-hidden="true" />
              {symbol}
              {symbols.length > 1 ? (
                <button type="button" className="chip__remove" aria-label={`Remove ${symbol} from the chart`} onClick={() => removeSymbol(symbol)}>
                  ×
                </button>
              ) : null}
            </li>
          ))}
        </ul>
        <SymbolPicker
          label={symbols.length >= MAX_COMPARED ? "Chart is full" : "Add an instrument to compare"}
          placeholder={symbols.length >= MAX_COMPARED ? `Up to ${MAX_COMPARED} at a time` : "Search to chart or compare"}
          disabled={symbols.length >= MAX_COMPARED}
          exclude={symbols}
          onPick={addSymbol}
        />
        <label className="toggle">
          <input type="checkbox" checked={percentMode} disabled={symbols.length > 1} onChange={(e) => setPercentView(e.target.checked)} />
          <span>% change</span>
        </label>
        {single && !percentMode ? (
          <>
            <label className="toggle">
              <input type="checkbox" checked={showSma.sma20} onChange={(e) => setShowSma({ ...showSma, sma20: e.target.checked })} />
              <span>20-day average</span>
            </label>
            <label className="toggle">
              <input type="checkbox" checked={showSma.sma50} onChange={(e) => setShowSma({ ...showSma, sma50: e.target.checked })} />
              <span>50-day average</span>
            </label>
          </>
        ) : null}
      </div>

      {suggestions.length > 0 ? (
        <div className="chip-row chip-row--suggest" role="group" aria-label="Quick picks">
          <span className="chip-row__label">Your assets</span>
          {suggestions.slice(0, 10).map((item) => (
            <button
              key={item.symbol}
              type="button"
              className={symbols.length === 1 && symbols[0] === item.symbol ? "chip chip--button chip--on" : "chip chip--button"}
              title={item.label}
              onClick={() => choose(item.symbol)}
            >
              {item.symbol}
            </button>
          ))}
        </div>
      ) : null}

      {(loading || waiting) && !view ? (
        <div className="data-state" role="status">Loading market history…</div>
      ) : !view ? (
        <div className="data-state data-state--error" role="alert">
          <strong>NOT AVAILABLE</strong>
          <span>
            {errors.length > 0
              ? errors.map((s) => `${s}: ${loaded[s]?.error}`).join(" ")
              : model?.sparse
                ? "The chosen instruments share fewer than two trading days in this range."
                : "No live or saved history for this selection."}
          </span>
        </div>
      ) : (
        <>
          {errors.length > 0 ? (
            <div className="inline-alert inline-alert--quiet" role="status">
              {errors.map((s) => `${s}: ${loaded[s]?.error}`).join(" ")} It is left off the chart.
            </div>
          ) : null}

          <div className="performance-metric">
            {usable.map((symbol, n) => {
              const s = stats[n];
              if (!s) return null;
              return (
                <span key={symbol} className="metric-series" style={{ color: "inherit" }}>
                  <strong>{usable.length > 1 ? symbol : money(s.last, currency(symbol))}</strong>
                  {s.changePercent !== null ? (
                    <span className={s.changePercent >= 0 ? "positive-text" : "negative-text"}>
                      {s.changePercent >= 0 ? "+" : ""}
                      {s.changePercent.toFixed(2)}%
                    </span>
                  ) : null}
                </span>
              );
            })}
            <small>{zoom ? "zoomed period" : "selected period"}</small>
            {zoom ? (
              <button type="button" className="secondary-button secondary-button--tight" onClick={() => setZoom(null)}>
                Reset zoom
              </button>
            ) : null}
          </div>

          <div className={loading ? "chart-wrap chart-wrap--busy" : "chart-wrap"} ref={frame} aria-busy={loading}>
            <div
              className="chart-interactive"
              tabIndex={0}
              role="group"
              aria-label={`${symbols.join(" and ")} ${range} chart. Use the arrow keys to read values, drag to zoom, Escape to reset.`}
              onKeyDown={onKey}
              onBlur={() => setCursor(null)}
            >
              <svg
                className="performance-chart performance-chart--interactive"
                width={width}
                height={HEIGHT}
                viewBox={`0 0 ${width} ${HEIGHT}`}
                onPointerMove={onPointerMove}
                onPointerDown={onPointerDown}
                onPointerUp={onPointerUp}
                onPointerLeave={() => {
                  setCursor(null);
                  setDrag(null);
                }}
                onDoubleClick={() => setZoom(null)}
                data-testid="market-chart-svg"
              >
                <defs>
                  <linearGradient id={fillId} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.20" />
                    <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
                  </linearGradient>
                </defs>
                {geometry?.yTicks.map((tick) => (
                  <g key={tick}>
                    <line className="chart-gridline" x1={0} x2={plotW} y1={geometry.y(tick)} y2={geometry.y(tick)} />
                    <text className="chart-axis-label" x={plotW + 8} y={geometry.y(tick) + 3}>
                      {axisNumber(tick, percentMode)}
                    </text>
                  </g>
                ))}
                {percentMode && geometry && view.min < 0 && view.max > 0 ? (
                  <line className="chart-zero" x1={0} x2={plotW} y1={geometry.y(0)} y2={geometry.y(0)} />
                ) : null}
                {geometry?.area ? <path d={geometry.area} fill={`url(#${fillId})`} /> : null}
                {geometry?.overlayPaths.map((o) => (
                  <path key={o.name} d={o.d} fill="none" className={o.name === "sma20" ? "chart-overlay chart-overlay--a" : "chart-overlay chart-overlay--b"} />
                ))}
                {geometry?.paths.map((d, n) => (
                  <path key={usable[n]} d={d} fill="none" className="chart-line chart-line--multi" style={{ stroke: SERIES_COLORS[n] }} />
                ))}
                {drag && geometry ? (
                  <rect
                    className="chart-selection"
                    x={geometry.x(Math.min(drag.from, drag.to))}
                    y={0}
                    width={Math.abs(geometry.x(drag.to) - geometry.x(drag.from))}
                    height={plotH}
                  />
                ) : null}
                {at !== null && geometry ? (
                  <g pointerEvents="none">
                    <line className="chart-cursor" x1={geometry.x(at)} x2={geometry.x(at)} y1={0} y2={plotH} />
                    {view.shown.map((values, n) =>
                      Number.isFinite(values[at]) ? (
                        <circle key={usable[n]} cx={geometry.x(at)} cy={geometry.y(values[at] as number)} r={4} className="chart-dot" style={{ stroke: SERIES_COLORS[n] }} />
                      ) : null,
                    )}
                  </g>
                ) : null}
                {geometry?.xTicks.map((tick) => (
                  <text key={`${tick.i}-${tick.label}`} className="chart-axis-label" x={geometry.x(tick.i)} y={HEIGHT - 6} textAnchor={tick.i === 0 ? "start" : tick.i === view.count - 1 ? "end" : "middle"}>
                    {tick.label}
                  </text>
                ))}
              </svg>
              {at !== null ? (
                <div
                  className="chart-tooltip"
                  data-testid="chart-readout"
                  style={{ left: Math.min(Math.max(8, (geometry?.x(at) ?? 0) + 12), Math.max(8, width - 230)) }}
                  aria-hidden="true"
                >
                  <strong>
                    {new Intl.DateTimeFormat("en-US", { weekday: "short", year: "numeric", month: "short", day: "2-digit" }).format(new Date(view.times[at] as number))}
                  </strong>
                  {usable.map((symbol, n) => {
                    const price = view.base[n]?.[at];
                    const pct = rebasePercent(view.base[n] ?? [])[at];
                    return (
                      <span key={symbol} className="chart-tooltip__row">
                        <i style={{ background: SERIES_COLORS[n] }} />
                        {symbol}
                        <b>{percentMode ? (Number.isFinite(pct) ? `${(pct as number) > 0 ? "+" : ""}${(pct as number).toFixed(2)}%` : "—") : money(price, currency(symbol))}</b>
                        {percentMode ? <small>{money(price, currency(symbol))}</small> : Number.isFinite(pct) ? <small>{`${(pct as number) > 0 ? "+" : ""}${(pct as number).toFixed(2)}%`}</small> : null}
                      </span>
                    );
                  })}
                </div>
              ) : null}
            </div>
            <p className="visually-hidden" aria-live="polite" data-testid="chart-live">
              {at !== null ? readoutText(at) : ""}
            </p>
          </div>

          {primaryStats && !percentMode ? (
            <dl className="chart-stats">
              <div><dt>Start</dt><dd>{money(primaryStats.first, currency(usable[0]))}</dd></div>
              <div><dt>High</dt><dd>{money(primaryStats.high, currency(usable[0]))}</dd></div>
              <div><dt>Low</dt><dd>{money(primaryStats.low, currency(usable[0]))}</dd></div>
              <div><dt>Days shown</dt><dd>{view.count}</dd></div>
            </dl>
          ) : null}

          <div className="chart-provenance">
            {primaryProvenance ? <FreshnessBadge provenance={primaryProvenance} /> : null}
            <p className="source-note">
              {usable
                .map((symbol) => {
                  const p = loaded[symbol]?.series?.provenance;
                  if (!p) return null;
                  return `${symbol}: ${p.source ?? "unknown source"}${p.last_known ? ` · LAST KNOWN DATA (saved ${p.saved_at ? dateTime(p.saved_at) : "earlier"}; providers could not be reached)` : " · retrieved"}`;
                })
                .filter(Boolean)
                .join("  |  ")}
              {primaryProvenance?.retrieved_at ? ` · Checked ${dateTime(primaryProvenance.retrieved_at)}` : ""}
            </p>
          </div>
        </>
      )}
    </section>
  );
}
