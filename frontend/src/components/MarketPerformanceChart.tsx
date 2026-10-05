import {
  useId,
  useMemo,
} from "react";

import type {
  MarketHistory,
  MarketRange,
} from "../types/market";

type Props = {
  history: MarketHistory | null;
  range: MarketRange;
  onRangeChange: (
    range: MarketRange,
  ) => void;
  loading: boolean;
  error: string | null;
};

const RANGES: MarketRange[] = [
  "1W",
  "1M",
  "3M",
  "1Y",
];

function toChartPoints(
  values: readonly number[],
  width: number,
  height: number,
  min: number,
  max: number,
) {
  const valueRange =
    max - min || 1;

  return values.map(
    (value, index) => ({
      x:
        (
          index /
          Math.max(
            1,
            values.length - 1,
          )
        ) * width,

      y:
        height -
        (
          (value - min) /
          valueRange
        ) *
          height,
    }),
  );
}

function dateLabel(
  value: string,
) {
  const date = new Date(value);

  return new Intl.DateTimeFormat(
    "en-US",
    {
      month: "short",
      day: "2-digit",
    },
  ).format(date);
}

export function MarketPerformanceChart({
  history,
  range,
  onRangeChange,
  loading,
  error,
}: Props) {
  const fillId = useId().replace(
    /:/g,
    "",
  );

  const width = 650;
  const height = 210;

  const chart = useMemo(() => {
    if (
      !history ||
      history.bars.length < 2
    ) {
      return null;
    }

    const values =
      history.bars.map(
        (bar) =>
          Number(bar.close),
      );

    const minRaw =
      Math.min(...values);

    const maxRaw =
      Math.max(...values);

    const padding =
      Math.max(
        1,
        (maxRaw - minRaw) * 0.18,
      );

    const min =
      minRaw - padding;

    const max =
      maxRaw + padding;

    const points =
      toChartPoints(
        values,
        width,
        height,
        min,
        max,
      );

    const line = points
      .map(
        (point) =>
          `${point.x.toFixed(
            1,
          )},${point.y.toFixed(1)}`,
      )
      .join(" ");

    const area =
      `0,${height} ` +
      `${line} ` +
      `${width},${height}`;

    const ticks =
      Array.from(
        { length: 4 },
        (_, index) =>
          max -
          (
            (max - min) /
            3
          ) *
            index,
      );

    const first =
      values[0];

    const latest =
      values[
        values.length - 1
      ];

    const changePercent =
      first === 0
        ? null
        : (
            (
              latest - first
            ) /
            first
          ) * 100;

    const endPoint =
      points[
        points.length - 1
      ];

    const labels = [
      history.bars[0],
      history.bars[
        Math.floor(
          history.bars.length / 2,
        )
      ],
      history.bars[
        history.bars.length - 1
      ],
    ].map((bar) =>
      dateLabel(bar.start_at),
    );

    return {
      line,
      area,
      ticks,
      latest,
      changePercent,
      endPoint,
      labels,
    };
  }, [history]);

  return (
    <section
      className="panel performance-panel"
      aria-labelledby="market-performance-title"
    >
      <div className="panel-heading panel-heading--chart">
        <div>
          <span className="section-kicker">
            MARKET PERFORMANCE
          </span>

          <h2 id="market-performance-title">
            {history?.symbol ??
              "Market history"}
          </h2>
        </div>

        <div
          className="range-tabs"
          aria-label="Chart range"
        >
          {RANGES.map((item) => (
            <button
              key={item}
              type="button"
              className={
                item === range
                  ? "range-tab range-tab--active"
                  : "range-tab"
              }
              aria-pressed={
                item === range
              }
              onClick={() =>
                onRangeChange(item)
              }
            >
              {item}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div
          className="data-state"
          role="status"
        >
          Loading market history…
        </div>
      ) : error ? (
        <div
          className="data-state data-state--error"
          role="alert"
        >
          <strong>
            Historical data unavailable
          </strong>
          <span>{error}</span>
        </div>
      ) : !chart ? (
        <div className="data-state">
          Historical market data is
          not available for this
          instrument.
        </div>
      ) : (
        <>
          <div className="performance-metric">
            <strong>
              {chart.latest.toLocaleString(
                "en-US",
                {
                  minimumFractionDigits:
                    2,
                  maximumFractionDigits:
                    2,
                },
              )}
            </strong>

            {chart.changePercent !==
            null ? (
              <span
                className={
                  chart.changePercent >=
                  0
                    ? "positive-text"
                    : "negative-text"
                }
              >
                {chart.changePercent >=
                0
                  ? "+"
                  : ""}
                {chart.changePercent.toFixed(
                  2,
                )}
                %
              </span>
            ) : null}

            <small>
              selected period
            </small>
          </div>

          <div
            className="chart-wrap"
            role="img"
            aria-label={
              `${history?.symbol} ` +
              `${range} market performance`
            }
          >
            <svg
              className="performance-chart"
              viewBox={
                `0 0 ${
                  width + 54
                } ${
                  height + 30
                }`
              }
              preserveAspectRatio="none"
            >
              <defs>
                <linearGradient
                  id={fillId}
                  x1="0"
                  y1="0"
                  x2="0"
                  y2="1"
                >
                  <stop
                    offset="0%"
                    stopColor="var(--accent)"
                    stopOpacity="0.20"
                  />
                  <stop
                    offset="100%"
                    stopColor="var(--accent)"
                    stopOpacity="0"
                  />
                </linearGradient>
              </defs>

              {chart.ticks.map(
                (tick, index) => {
                  const y =
                    (
                      index /
                      3
                    ) *
                    height;

                  return (
                    <g
                      key={`${tick}-${index}`}
                    >
                      <line
                        className="chart-gridline"
                        x1="0"
                        x2={width}
                        y1={y}
                        y2={y}
                      />

                      <text
                        className="chart-axis-label"
                        x={
                          width +
                          14
                        }
                        y={y + 4}
                      >
                        {Math.round(
                          tick,
                        ).toLocaleString(
                          "en-US",
                        )}
                      </text>
                    </g>
                  );
                },
              )}

              <polygon
                points={chart.area}
                fill={
                  `url(#${fillId})`
                }
              />

              <polyline
                className="chart-line"
                points={chart.line}
                fill="none"
              />

              <circle
                className="chart-endpoint"
                cx={
                  chart.endPoint.x
                }
                cy={
                  chart.endPoint.y
                }
                r="4"
              />
            </svg>

            <div
              className="chart-dates"
              aria-hidden="true"
            >
              {chart.labels.map(
                (label, index) => (
                  <span
                    key={
                      `${label}-${index}`
                    }
                  >
                    {label}
                  </span>
                ),
              )}
            </div>
          </div>

          <p className="source-note">
            Source:{" "}
            {history?.data_mode ??
              "unknown"}
            {" · "}
            Updated{" "}
            {history
              ? new Date(
                  history.generated_at,
                ).toLocaleString()
              : "—"}
          </p>
        </>
      )}
    </section>
  );
}
