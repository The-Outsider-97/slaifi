import { useMemo, useState } from "react";

import type { Watchlist } from "../hooks/useWatchlist";
import { dateTime, humanize, money, signedPercent } from "../lib/format";
import type { MarketQuote } from "../types/market";
import { SymbolPicker } from "./SymbolPicker";

type Props = {
  /** The user's own assets. */
  watchlist: Watchlist;
  /** Default market indicators, shown only while the watchlist is empty. */
  indicators: MarketQuote[];
  /** Indicator symbols with no live and no saved quote: listed as NOT AVAILABLE, never filled in. */
  unavailable?: string[];
  /** Asset classes the active strategy prefers (shown as a filter). */
  preferredClasses?: readonly string[];
  loading: boolean;
  /** Show this symbol on the chart. */
  onChart?: (symbol: string) => void;
};

type Row = {
  key: string;
  symbol: string;
  display: string;
  assetClass: string;
  price: string | null;
  currency: string | null;
  /** A fraction (0.0132 is +1.32 %). */
  change: number | null;
  source: string | null;
  lastKnown: boolean;
  observedAt: string | null;
  own: boolean;
};

const PREFERRED = "__preferred__";

export function MarketWatchTable({ watchlist, indicators, unavailable = [], preferredClasses = [], loading, onChart }: Props) {
  const [filter, setFilter] = useState("all");
  const own = watchlist.items.length > 0;

  const rows = useMemo<Row[]>(() => {
    if (own) {
      return watchlist.items.map((item) => {
        const q = item.quote;
        const available = q?.available === true && q.price !== null;
        return {
          key: `own:${item.asset.symbol}`,
          symbol: item.asset.symbol,
          display: item.asset.display_symbol,
          assetClass: item.asset.asset_class,
          price: available ? q.price : null,
          currency: q?.currency ?? item.asset.currency,
          change: available ? q.change_rate : null,
          source: available ? q.source : null,
          lastKnown: available ? q.last_known : false,
          observedAt: available ? q.observed_at : null,
          own: true,
        };
      });
    }
    const quoted: Row[] = indicators.map((quote) => ({
      key: `ind:${quote.asset_class}:${quote.symbol}`,
      symbol: quote.symbol,
      display: quote.symbol,
      assetClass: quote.asset_class,
      price: quote.price,
      currency: quote.currency,
      change: quote.change_percent === null ? null : Number(quote.change_percent) / 100,
      source: quote.source,
      lastKnown: quote.last_known,
      observedAt: quote.observed_at,
      own: false,
    }));
    const missing: Row[] = unavailable.map((symbol) => ({
      key: `na:${symbol}`,
      symbol,
      display: symbol,
      assetClass: "",
      price: null,
      currency: null,
      change: null,
      source: null,
      lastKnown: false,
      observedAt: null,
      own: false,
    }));
    return [...quoted, ...missing];
  }, [own, watchlist.items, indicators, unavailable]);

  const classes = useMemo(() => [...new Set(rows.map((r) => r.assetClass).filter(Boolean))].sort(), [rows]);
  const shown = rows.filter((row) => {
    if (filter === "all") return true;
    if (filter === PREFERRED) return preferredClasses.includes(row.assetClass);
    return row.assetClass === filter;
  });
  const taken = rows.filter((r) => r.own).map((r) => r.symbol);

  return (
    <section className="panel watch-panel" aria-labelledby="market-watch-title">
      <div className="panel-heading">
        <div>
          <span className="section-kicker">{own ? "ON YOUR RADAR" : "MARKET INDICATORS"}</span>
          <h2 id="market-watch-title">Market watch</h2>
        </div>
        <select
          className="asset-filter"
          aria-label="Filter market watch"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
        >
          <option value="all">All assets</option>
          {preferredClasses.length > 0 ? <option value={PREFERRED}>Preferred by my strategy</option> : null}
          {classes.map((c) => (
            <option key={c} value={c}>{humanize(c)}</option>
          ))}
        </select>
      </div>

      <div className="watch-add">
        <SymbolPicker
          label="Add an asset to follow"
          placeholder="Add an asset you follow (name or ticker)"
          exclude={taken}
          disabled={watchlist.busy}
          onPick={(symbol) => void watchlist.add(symbol)}
        />
      </div>
      {!own && !loading && !watchlist.loading ? (
        <p className="watch-note" data-testid="watch-default-note">
          Showing default market indicators. Add the assets you follow and this list becomes yours.
        </p>
      ) : null}
      {watchlist.actionError ? <p className="field-error" role="alert">{watchlist.actionError}</p> : null}
      {watchlist.error ? <p className="field-error" role="alert">Your list could not be loaded: {watchlist.error}</p> : null}

      {loading || watchlist.loading ? (
        <div className="data-state">Loading market data…</div>
      ) : shown.length === 0 ? (
        <div className="data-state">NOT AVAILABLE · nothing to show for this filter.</div>
      ) : (
        <div className="watch-table" role="table" aria-label="Market watch">
          <div className="watch-row watch-row--header" role="row">
            <span role="columnheader">Asset</span>
            <span role="columnheader">Price</span>
            <span role="columnheader">Day change</span>
            <span role="columnheader">Source</span>
            <span aria-hidden="true" />
          </div>
          {shown.map((row) => {
            const change = row.change;
            const direction = change === null || change === 0 ? "neutral" : change > 0 ? "positive" : "negative";
            const unavailableRow = row.price === null;
            return (
              <div className="watch-row" role="row" key={row.key} data-testid={unavailableRow ? "watch-unavailable" : undefined}>
                <div className="watch-asset" role="cell">
                  <span className="ticker-badge">{row.display[0] ?? "•"}</span>
                  <span>
                    <strong>{row.display}</strong>
                    {row.assetClass ? <small>{row.assetClass}</small> : null}
                  </span>
                </div>
                {unavailableRow ? (
                  <strong className="not-available" role="cell">NOT AVAILABLE</strong>
                ) : (
                  <strong className="watch-price" role="cell">{money(row.price, row.currency ?? "USD")}</strong>
                )}
                <span className={`market-change market-change--${direction}`} role="cell">
                  {change === null ? "—" : signedPercent(change)}
                </span>
                <span role="cell" className="watch-source">
                  {row.source ?? "none"}
                  {row.lastKnown ? (
                    <small className="last-known-note" data-testid="watch-last-known">
                      {" "}
                      · last known{row.observedAt ? ` ${dateTime(row.observedAt)}` : ""}
                    </small>
                  ) : null}
                </span>
                <span className="row-actions" role="cell">
                  {onChart ? (
                    <button type="button" className="icon-button" aria-label={`Show ${row.display} on the chart`} title="Show on chart" onClick={() => onChart(row.symbol)}>
                      ◔
                    </button>
                  ) : null}
                  <a className="row-action" href={`#/analysis/${encodeURIComponent(row.symbol)}`} aria-label={`Analyse ${row.display}`} title="Open analysis">↗</a>
                  {row.own ? (
                    <button
                      type="button"
                      className="icon-button"
                      aria-label={`Stop following ${row.display}`}
                      title="Remove from my list"
                      disabled={watchlist.busy}
                      onClick={() => void watchlist.remove(row.symbol)}
                    >
                      ×
                    </button>
                  ) : null}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
