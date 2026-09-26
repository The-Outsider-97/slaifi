import { MARKET_WATCH_ROWS } from "../data/demoMarket";
import { StatusBadge } from "./StatusBadge";

export function MarketWatchTable() {
  return (
    <section className="panel watch-panel" aria-labelledby="market-watch-title">
      <div className="panel-heading">
        <div>
          <span className="section-kicker">ON YOUR RADAR</span>
          <h2 id="market-watch-title">Market watch</h2>
        </div>
        <select className="asset-filter" aria-label="Filter market watch">
          <option>All assets</option>
          <option>Equities</option>
          <option>ETFs</option>
        </select>
      </div>
      <div className="watch-note">Illustrative sample signals — not recommendations.</div>
      <div className="watch-table" role="table" aria-label="Illustrative market watch">
        <div className="watch-row watch-row--header" role="row">
          <span role="columnheader">Asset</span>
          <span role="columnheader">Price</span>
          <span role="columnheader">Day change</span>
          <span role="columnheader">Sample signal</span>
          <span aria-hidden="true" />
        </div>
        {MARKET_WATCH_ROWS.map((row) => {
          const direction = row.changePercent > 0 ? "positive" : row.changePercent < 0 ? "negative" : "neutral";
          return (
            <div className="watch-row" role="row" key={row.symbol}>
              <div className="watch-asset" role="cell">
                <span className="ticker-badge">{row.symbol[0]}</span>
                <span><strong>{row.symbol}</strong><small>{row.name}</small></span>
              </div>
              <strong className="watch-price" role="cell">${row.price.toFixed(2)}</strong>
              <span className={`market-change market-change--${direction}`} role="cell">
                {row.changePercent > 0 ? "+" : ""}{row.changePercent.toFixed(2)}%
              </span>
              <span role="cell"><StatusBadge status={row.signal} /></span>
              <a className="row-action" href={`#${row.symbol.toLowerCase()}`} aria-label={`Open ${row.symbol}`}>↗</a>
            </div>
          );
        })}
      </div>
    </section>
  );
}
