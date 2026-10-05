import {
  useMemo,
  useState,
} from "react";

import type {
  MarketQuote,
} from "../types/market";

type Props = {
  quotes: MarketQuote[];
  loading: boolean;
};

function formatPrice(
  quote: MarketQuote,
) {
  const value =
    Number(quote.price);

  try {
    return new Intl.NumberFormat(
      "en-US",
      {
        style: "currency",
        currency: quote.currency,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      },
    ).format(value);
  } catch {
    return value.toFixed(2);
  }
}

export function MarketWatchTable({
  quotes,
  loading,
}: Props) {
  const [
    filter,
    setFilter,
  ] = useState("all");

  const rows = useMemo(
    () =>
      filter === "all"
        ? quotes
        : quotes.filter(
            (quote) =>
              quote.asset_class ===
              filter,
          ),
    [quotes, filter],
  );

  return (
    <section
      className="panel watch-panel"
      aria-labelledby="market-watch-title"
    >
      <div className="panel-heading">
        <div>
          <span className="section-kicker">
            ON YOUR RADAR
          </span>

          <h2 id="market-watch-title">
            Market watch
          </h2>
        </div>

        <select
          className="asset-filter"
          aria-label="Filter market watch"
          value={filter}
          onChange={(event) =>
            setFilter(
              event.target.value,
            )
          }
        >
          <option value="all">
            All assets
          </option>
          <option value="equity">
            Equities
          </option>
          <option value="etf">
            ETFs
          </option>
          <option value="index">
            Indices
          </option>
        </select>
      </div>

      {loading ? (
        <div className="data-state">
          Loading market data…
        </div>
      ) : rows.length === 0 ? (
        <div className="data-state">
          No market data is
          available for this filter.
        </div>
      ) : (
        <div
          className="watch-table"
          role="table"
          aria-label="Market watch"
        >
          <div
            className="watch-row watch-row--header"
            role="row"
          >
            <span role="columnheader">
              Asset
            </span>
            <span role="columnheader">
              Price
            </span>
            <span role="columnheader">
              Day change
            </span>
            <span role="columnheader">
              Source
            </span>
            <span
              aria-hidden="true"
            />
          </div>

          {rows.map((row) => {
            const change =
              row.change_percent ===
              null
                ? null
                : Number(
                    row.change_percent,
                  );

            const direction =
              change === null
                ? "neutral"
                : change > 0
                  ? "positive"
                  : change < 0
                    ? "negative"
                    : "neutral";

            return (
              <div
                className="watch-row"
                role="row"
                key={
                  `${row.asset_class}:${row.symbol}`
                }
              >
                <div
                  className="watch-asset"
                  role="cell"
                >
                  <span className="ticker-badge">
                    {row.symbol[0] ??
                      "•"}
                  </span>

                  <span>
                    <strong>
                      {row.symbol}
                    </strong>
                    <small>
                      {row.asset_class}
                    </small>
                  </span>
                </div>

                <strong
                  className="watch-price"
                  role="cell"
                >
                  {formatPrice(row)}
                </strong>

                <span
                  className={
                    `market-change ` +
                    `market-change--${direction}`
                  }
                  role="cell"
                >
                  {change === null
                    ? "—"
                    : `${
                        change >
                        0
                          ? "+"
                          : ""
                      }${change.toFixed(
                        2,
                      )}%`}
                </span>

                <span
                  role="cell"
                  className="watch-source"
                >
                  {row.source}
                </span>

                <span
                  className="row-action"
                  aria-label={
                    `${row.symbol} updated ` +
                    `${new Date(
                      row.observed_at,
                    ).toLocaleString()}`
                  }
                >
                  ↗
                </span>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
