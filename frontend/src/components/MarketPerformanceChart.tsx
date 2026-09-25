import { useId, useMemo, useState } from "react";

import { ILLUSTRATIVE_RANGES, type MarketRange } from "../data/demoMarket";

function toChartPoints(values: readonly number[], width: number, height: number, min: number, max: number) {
  const range = max - min || 1;
  return values.map((value, index) => ({
    x: (index / Math.max(1, values.length - 1)) * width,
    y: height - ((value - min) / range) * height,
  }));
}

export function MarketPerformanceChart() {
  const [range, setRange] = useState<MarketRange>("3M");
  const fillId = useId().replace(/:/g, "");
  const data = ILLUSTRATIVE_RANGES[range];
  const width = 650;
  const height = 210;
  const chart = useMemo(() => {
    const minRaw = Math.min(...data.values);
    const maxRaw = Math.max(...data.values);
    const padding = Math.max(1, (maxRaw - minRaw) * 0.18);
    const min = minRaw - padding;
    const max = maxRaw + padding;
    const points = toChartPoints(data.values, width, height, min, max);
    const line = points.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
    const area = `0,${height} ${line} ${width},${height}`;
    const ticks = Array.from({ length: 4 }, (_, index) => max - ((max - min) / 3) * index);
    return { line, area, ticks };
  }, [data]);
  const latest = data.values[data.values.length - 1];

  return (
    <section className="panel performance-panel" aria-labelledby="market-performance-title">
      <div className="panel-heading panel-heading--chart">
        <div>
          <span className="section-kicker">MARKET PERFORMANCE</span>
          <h2 id="market-performance-title">S&amp;P 500 <span>/ SPX</span></h2>
        </div>
        <div className="range-tabs" aria-label="Chart range">
          {(Object.keys(ILLUSTRATIVE_RANGES) as MarketRange[]).map((item) => (
            <button
              key={item}
              type="button"
              className={item === range ? "range-tab range-tab--active" : "range-tab"}
              aria-pressed={item === range}
              onClick={() => setRange(item)}
            >
              {item}
            </button>
          ))}
        </div>
      </div>

      <div className="performance-metric">
        <strong>{latest.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong>
        <span className={data.changePercent >= 0 ? "positive-text" : "negative-text"}>
          {data.changePercent >= 0 ? "+" : ""}{data.changePercent.toFixed(2)}%
        </span>
        <small>{data.periodLabel}</small>
      </div>

      <div className="chart-wrap" role="img" aria-label={`Illustrative S&P 500 ${range} performance chart`}>
        <svg className="performance-chart" viewBox={`0 0 ${width + 54} ${height + 30}`} preserveAspectRatio="none">
          <defs>
            <linearGradient id={fillId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.20" />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
            </linearGradient>
          </defs>
          {chart.ticks.map((tick, index) => {
            const y = (index / 3) * height;
            return (
              <g key={tick}>
                <line className="chart-gridline" x1="0" x2={width} y1={y} y2={y} />
                <text className="chart-axis-label" x={width + 14} y={y + 4}>{Math.round(tick).toLocaleString("en-US")}</text>
              </g>
            );
          })}
          <polygon points={chart.area} fill={`url(#${fillId})`} />
          <polyline className="chart-line" points={chart.line} fill="none" />
          <circle className="chart-endpoint" cx={width} cy={chart.line ? Number(chart.line.split(" ").at(-1)?.split(",")[1]) : 0} r="4" />
        </svg>
        <div className="chart-dates" aria-hidden="true">
          {data.labels.map((label) => <span key={label}>{label}</span>)}
        </div>
      </div>

      <p className="source-note">Illustrative data · Not a live market feed</p>
    </section>
  );
}
