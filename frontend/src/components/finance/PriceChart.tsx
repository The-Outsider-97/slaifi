import { useId, useMemo, useState, type KeyboardEvent, type PointerEvent } from "react";

import { dateTime, money, number, shortDate } from "../../lib/format";
import type { Bar } from "../../types/finance";

export type ChartKind = "line" | "candles";

type Props = {
  bars: Bar[];
  overlays: Record<string, (number | null)[]>;
  kind: ChartKind;
  currency: string;
  label: string;
};

const W = 800;
const PRICE_H = 260;
const VOLUME_H = 56;
const GAP = 16;
const H = PRICE_H + GAP + VOLUME_H;
const PAD_RIGHT = 56;

const OVERLAY_CLASS: Record<string, string> = { sma20: "chart-overlay chart-overlay--a", sma50: "chart-overlay chart-overlay--b" };
const OVERLAY_LABEL: Record<string, string> = { sma20: "SMA 20", sma50: "SMA 50" };

/**
 * Price chart with optional candles, volume and moving-average overlays.
 *
 * Only values the API returned are drawn. Missing volume is left blank rather than estimated, and
 * the readout is reachable with the keyboard (arrow keys) as well as the pointer.
 */
export function PriceChart({ bars, overlays, kind, currency, label }: Props) {
  const titleId = useId();
  const [cursor, setCursor] = useState<number | null>(null);

  const model = useMemo(() => {
    const parsed = bars.map((bar) => ({
      open: Number(bar.open),
      high: Number(bar.high),
      low: Number(bar.low),
      close: Number(bar.close),
      volume: bar.volume === null ? null : Number(bar.volume),
    }));
    const usable = parsed.every((row) => [row.open, row.high, row.low, row.close].every(Number.isFinite));
    const lows = parsed.map((row) => row.low);
    const highs = parsed.map((row) => row.high);
    let min = Math.min(...lows);
    let max = Math.max(...highs);
    for (const [name, values] of Object.entries(overlays)) {
      if (!(name in OVERLAY_CLASS)) continue;
      for (const v of values) {
        if (v !== null && Number.isFinite(v)) {
          min = Math.min(min, v);
          max = Math.max(max, v);
        }
      }
    }
    const span = max - min || Math.max(1, Math.abs(max) * 0.01);
    min -= span * 0.05;
    max += span * 0.05;
    const volumes = parsed.map((row) => row.volume ?? 0);
    const maxVolume = Math.max(...volumes, 0);
    return { parsed, usable, min, max, maxVolume };
  }, [bars, overlays]);

  if (bars.length < 2 || !model.usable) {
    return <div className="data-state">There is not enough valid price history to draw a chart.</div>;
  }

  const plotW = W - PAD_RIGHT;
  const step = plotW / Math.max(1, bars.length - 1);
  const x = (i: number) => i * step;
  const y = (value: number) => PRICE_H - ((value - model.min) / (model.max - model.min)) * PRICE_H;
  const candleW = Math.max(1, Math.min(10, step * 0.62));

  const path = (values: (number | null)[]) => {
    let d = "";
    let pen = false;
    values.forEach((v, i) => {
      if (v === null || !Number.isFinite(v)) {
        pen = false;
        return;
      }
      d += `${pen ? "L" : "M"}${x(i).toFixed(2)} ${y(v).toFixed(2)} `;
      pen = true;
    });
    return d.trim();
  };

  const closeValues = model.parsed.map((row) => row.close);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => model.min + (model.max - model.min) * (1 - t));
  const first = model.parsed[0].close;
  const last = model.parsed[model.parsed.length - 1].close;
  const tone = last >= first ? "up" : "down";
  const active = cursor === null ? null : Math.min(Math.max(cursor, 0), bars.length - 1);
  const shown = active === null ? bars.length - 1 : active;
  const row = model.parsed[shown];

  const fromPointer = (event: PointerEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = (event.clientX - rect.left) / rect.width;
    const index = Math.round(((ratio * W) / plotW) * (bars.length - 1));
    setCursor(Math.min(Math.max(index, 0), bars.length - 1));
  };

  const onKey = (event: KeyboardEvent<SVGSVGElement>) => {
    const at = cursor ?? bars.length - 1;
    if (event.key === "ArrowLeft") setCursor(Math.max(0, at - 1));
    else if (event.key === "ArrowRight") setCursor(Math.min(bars.length - 1, at + 1));
    else if (event.key === "Home") setCursor(0);
    else if (event.key === "End") setCursor(bars.length - 1);
    else if (event.key === "Escape") setCursor(null);
    else return;
    event.preventDefault();
  };

  const legend = Object.keys(overlays).filter((name) => name in OVERLAY_CLASS);

  return (
    <figure className="price-chart">
      <figcaption id={titleId} className="price-chart__readout" aria-live="polite">
        <strong>{dateTime(bars[shown].end_at)}</strong>
        <span>O {money(row.open, currency)}</span>
        <span>H {money(row.high, currency)}</span>
        <span>L {money(row.low, currency)}</span>
        <span>C {money(row.close, currency)}</span>
        <span>Vol {row.volume === null ? "—" : number(row.volume, 0)}</span>
      </figcaption>

      <svg
        className="price-chart__svg"
        viewBox={`0 0 ${W} ${H + 18}`}
        role="img"
        aria-labelledby={titleId}
        aria-label={`${label}: ${bars.length} bars from ${shortDate(bars[0].start_at)} to ${shortDate(bars[bars.length - 1].end_at)}. Use the arrow keys to move between bars.`}
        tabIndex={0}
        onPointerMove={fromPointer}
        onPointerLeave={() => setCursor(null)}
        onKeyDown={onKey}
        onBlur={() => setCursor(null)}
      >
        {ticks.map((tick) => (
          <g key={tick}>
            <line className="chart-gridline" x1={0} x2={plotW} y1={y(tick)} y2={y(tick)} />
            <text className="chart-axis-label" x={plotW + 6} y={y(tick) + 3}>
              {number(tick, tick >= 1000 ? 0 : 2)}
            </text>
          </g>
        ))}

        {kind === "line" ? (
          <path className={`chart-line chart-line--${tone}`} d={path(closeValues)} fill="none" />
        ) : (
          model.parsed.map((p, i) => {
            const up = p.close >= p.open;
            const top = y(Math.max(p.open, p.close));
            const bottom = y(Math.min(p.open, p.close));
            return (
              <g key={i} className={up ? "candle candle--up" : "candle candle--down"}>
                <line x1={x(i)} x2={x(i)} y1={y(p.high)} y2={y(p.low)} />
                <rect x={x(i) - candleW / 2} y={top} width={candleW} height={Math.max(1, bottom - top)} />
              </g>
            );
          })
        )}

        {legend.map((name) => (
          <path key={name} className={OVERLAY_CLASS[name]} d={path(overlays[name])} fill="none" />
        ))}

        {model.parsed.map((p, i) =>
          p.volume === null || model.maxVolume === 0 ? null : (
            <rect
              key={`v${i}`}
              className={p.close >= p.open ? "volume-bar volume-bar--up" : "volume-bar volume-bar--down"}
              x={x(i) - Math.max(0.5, step * 0.35)}
              width={Math.max(1, step * 0.7)}
              y={PRICE_H + GAP + VOLUME_H - (p.volume / model.maxVolume) * VOLUME_H}
              height={(p.volume / model.maxVolume) * VOLUME_H}
            />
          ),
        )}

        {active !== null ? (
          <g pointerEvents="none">
            <line className="chart-cursor" x1={x(active)} x2={x(active)} y1={0} y2={H} />
            <circle className="chart-endpoint" cx={x(active)} cy={y(row.close)} r={3.5} />
          </g>
        ) : null}

        <text className="chart-axis-label" x={0} y={H + 12}>
          {shortDate(bars[0].start_at)}
        </text>
        <text className="chart-axis-label" x={plotW} y={H + 12} textAnchor="end">
          {shortDate(bars[bars.length - 1].end_at)}
        </text>
      </svg>

      {legend.length ? (
        <ul className="chart-legend" aria-label="Chart overlays">
          {legend.map((name) => (
            <li key={name}>
              <span className={`chart-legend__swatch ${OVERLAY_CLASS[name]}`} aria-hidden="true" />
              {OVERLAY_LABEL[name] ?? name}
            </li>
          ))}
        </ul>
      ) : null}
    </figure>
  );
}
