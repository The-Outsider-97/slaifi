import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import { AppShell } from "../components/AppShell";
import { Explained } from "../components/finance/Explained";
import { FreshnessBadge } from "../components/finance/FreshnessBadge";
import { Empty, Loading, Notice } from "../components/finance/Notice";
import { PageHeading } from "../components/finance/PageHeading";
import { PriceChart, type ChartKind } from "../components/finance/PriceChart";
import { useAction, useAsync } from "../hooks/useAsync";
import { dateTime, direction, humanize, money, number, percent, signalLabel, signedPercent } from "../lib/format";
import {
  addToWatchlist,
  fetchBacktest,
  fetchComparison,
  fetchQuote,
  fetchRecommendation,
  fetchSeries,
  fetchStats,
  fetchStrategies,
  fetchWatchlist,
  marketMeta,
  removeFromWatchlist,
  searchInstruments,
} from "../services/finance";
import type { Instrument, RecommendationReport } from "../types/finance";

const DEFAULT_RANGES = ["1M", "3M", "6M", "1Y", "5Y"];
const DEFAULT_INTERVALS = ["1day", "1week", "1month"];
const INTERVAL_LABEL: Record<string, string> = {
  "1min": "1 min",
  "5min": "5 min",
  "15min": "15 min",
  "30min": "30 min",
  "1h": "1 hour",
  "4h": "4 hours",
  "1day": "Daily",
  "1week": "Weekly",
  "1month": "Monthly",
};

function SymbolSearch({ onPick }: { onPick: (symbol: string) => void }) {
  const [text, setText] = useState("");
  const [results, setResults] = useState<Instrument[] | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const search = useAction(searchInstruments);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const query = text.trim();
    if (!query) return;
    const found = await search.run(query);
    if (found) {
      setResults(found.results);
      setNote(found.results.length === 0 ? `No instruments matched “${query}”.` : null);
    }
  };

  return (
    <section className="panel analysis-search" aria-labelledby="search-title">
      <h2 id="search-title" className="visually-hidden">
        Search instruments
      </h2>
      <form className="inline-form" onSubmit={submit} role="search">
        <label className="field field--grow">
          <span>Symbol or name</span>
          <input
            type="search"
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="e.g. AAPL, microsoft"
            maxLength={64}
            autoComplete="off"
          />
        </label>
        <button className="secondary-button" type="submit" disabled={search.running || !text.trim()}>
          {search.running ? "Searching…" : "Search"}
        </button>
      </form>
      {search.error ? <Notice tone="error">{search.error}</Notice> : null}
      {note ? <Notice>{note}</Notice> : null}
      {results && results.length > 0 ? (
        <ul className="result-list" aria-label="Search results">
          {results.map((item) => (
            <li key={`${item.asset.symbol}-${item.asset.exchange}`}>
              <button type="button" className="result-item" onClick={() => onPick(item.asset.symbol)}>
                <strong>{item.asset.display_symbol}</strong>
                <span>{item.name ?? "Unnamed instrument"}</span>
                <small>
                  {[item.asset.exchange, item.instrument_type].filter(Boolean).join(" · ")}
                  {item.illustrative ? " · illustrative" : ""}
                </small>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function ActionBadge({ report }: { report: RecommendationReport }) {
  if (report.status !== "recommendation" || !report.action) {
    return <span className="status-badge status-badge--insufficient">INSUFFICIENT EVIDENCE</span>;
  }
  const tone = report.action === "BUY" || report.action === "DCA" ? "dca" : report.action === "SELL" || report.action === "AVOID" || report.action === "REDUCE" ? "review-risk" : "hold";
  return <span className={`status-badge status-badge--${tone}`}>{report.action}</span>;
}

function RecommendationPanel({ symbol, strategyId, portfolioId }: { symbol: string; strategyId: string | null; portfolioId: string | null }) {
  const [explain, setExplain] = useState(false);
  const key = `${symbol}|${strategyId}|${portfolioId}|${explain}`;
  const rec = useAsync((signal) => fetchRecommendation(symbol, { strategyId, portfolioId, explain }, signal), key);
  const back = useAsync((signal) => fetchBacktest(symbol, strategyId, signal), `${symbol}|${strategyId}`);

  return (
    <section className="panel analysis-panel" aria-labelledby="rec-title">
      <div className="panel-heading">
        <div>
          <span className="section-kicker">RULE-BASED ASSESSMENT</span>
          <h2 id="rec-title">Recommendation</h2>
        </div>
        {rec.data ? <ActionBadge report={rec.data.report} /> : null}
      </div>

      {rec.loading && !rec.data ? <Loading label="Evaluating the evidence…" /> : null}
      {rec.error ? <Notice tone="error" title="Recommendation unavailable" onRetry={rec.reload}>{rec.error}</Notice> : null}

      {rec.data ? (
        <div className="stack">
          <p className="lead">{rec.data.report.summary}</p>

          {rec.data.report.status !== "recommendation" ? (
            <Notice tone="warning" title="No recommendation is made">
              {rec.data.report.insufficient_reasons.join(" ")}
            </Notice>
          ) : (
            <dl className="facts">
              <div>
                <dt>Signal score</dt>
                <dd>{number(rec.data.report.signal_score, 2)}</dd>
                <small>{rec.data.report.score_note}</small>
              </div>
              <div>
                <dt>Strategy</dt>
                <dd>{rec.data.strategy.name}</dd>
                <small>Horizon {rec.data.report.horizon_days} days</small>
              </div>
              <div>
                <dt>Risk level</dt>
                <dd>{rec.data.report.risk_level ? humanize(rec.data.report.risk_level) : "—"}</dd>
              </div>
              <div>
                <dt>Evidence</dt>
                <dd>{rec.data.report.observation_count} bars</dd>
                <small>Last bar {dateTime(rec.data.report.last_bar_at)}</small>
              </div>
            </dl>
          )}

          {rec.data.report.signals.length ? (
            <div className="signal-table" role="table" aria-label="Signals">
              <div className="signal-row signal-row--header" role="row">
                <span role="columnheader">Signal</span>
                <span role="columnheader">Reading</span>
                <span role="columnheader">Direction</span>
                <span role="columnheader">Why</span>
              </div>
              {rec.data.report.signals.map((signal) => (
                <div className="signal-row" role="row" key={signal.name}>
                  <strong role="cell">{signalLabel(signal.name)}</strong>
                  <span role="cell">{signal.value === null ? "—" : number(signal.value, 2)}</span>
                  <span role="cell" className={`market-change market-change--${signal.vote > 0 ? "positive" : signal.vote < 0 ? "negative" : "neutral"}`}>
                    {humanize(signal.direction)}
                  </span>
                  <span role="cell">{signal.rationale}</span>
                </div>
              ))}
            </div>
          ) : null}

          {rec.data.report.supporting_signals.length || rec.data.report.conflicting_signals.length ? (
            <div className="two-col">
              <div>
                <h3>Supporting</h3>
                <ul className="plain-list">
                  {rec.data.report.supporting_signals.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </div>
              <div>
                <h3>Conflicting</h3>
                <ul className="plain-list">
                  {rec.data.report.conflicting_signals.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </div>
            </div>
          ) : null}

          {rec.data.report.constraint_findings.length ? (
            <div>
              <h3>Strategy limits</h3>
              <ul className="plain-list">
                {rec.data.report.constraint_findings.map((f) => (
                  <li key={f.code + f.message} className={f.severity === "breach" ? "negative-text" : undefined}>
                    {f.message}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {rec.data.report.invalidation_conditions.length ? (
            <div>
              <h3>What would invalidate this</h3>
              <ul className="plain-list">
                {rec.data.report.invalidation_conditions.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {rec.data.report.prediction?.interval ? (
            <div className="prediction">
              <h3>Validated return interval</h3>
              <p>
                Over {rec.data.report.prediction.horizon_days} days, between{" "}
                <strong>{signedPercent(rec.data.report.prediction.interval.lower_return_rate)}</strong> and{" "}
                <strong>{signedPercent(rec.data.report.prediction.interval.upper_return_rate)}</strong> (nominal{" "}
                {percent(rec.data.report.prediction.interval.nominal_coverage, 0)} interval).
              </p>
              <small>
                Model {rec.data.report.prediction.model.name} v{rec.data.report.prediction.model.version}.{" "}
                {rec.data.report.prediction_validation
                  ? `Walk-forward coverage ${percent(rec.data.report.prediction_validation.realized_coverage, 1)} over ${rec.data.report.prediction_validation.test_count} tests. `
                  : ""}
                This is a historical-return range, not a probability of any outcome.
              </small>
            </div>
          ) : rec.data.report.status === "recommendation" ? (
            <p className="muted">
              No forecast is shown: the interval method did not pass its walk-forward validation on this history, so no prediction is
              claimed.
            </p>
          ) : null}

          <label className="check">
            <input type="checkbox" checked={explain} onChange={(event) => setExplain(event.target.checked)} />
            <span>Ask SLAI to explain this result</span>
          </label>
          <Explained explanation={rec.data.explanation} />

          <details className="disclosure">
            <summary>Historical simulation of this strategy</summary>
            {back.loading ? <Loading label="Running the simulation…" /> : null}
            {back.error ? <Notice tone="error" onRetry={back.reload}>{back.error}</Notice> : null}
            {back.data?.message ? <Notice tone="warning">{back.data.message}</Notice> : null}
            {back.data?.result ? (
              <div className="stack">
                <dl className="facts">
                  <div>
                    <dt>Strategy return</dt>
                    <dd>{signedPercent(back.data.result.total_return)}</dd>
                    <small>Max drawdown {percent(back.data.result.max_drawdown)}</small>
                  </div>
                  <div>
                    <dt>{back.data.result.benchmark.label}</dt>
                    <dd>{signedPercent(back.data.result.benchmark.total_return)}</dd>
                    <small>Max drawdown {percent(back.data.result.benchmark.max_drawdown)}</small>
                  </div>
                  <div>
                    <dt>Excess return</dt>
                    <dd>{signedPercent(back.data.result.excess_return)}</dd>
                  </div>
                  <div>
                    <dt>Trades</dt>
                    <dd>{back.data.result.trade_count}</dd>
                    <small>Win rate {percent(back.data.result.win_rate, 0)}</small>
                  </div>
                </dl>
                <ul className="plain-list">
                  {back.data.result.assumptions.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
                <small className="muted">{back.data.disclaimer}</small>
              </div>
            ) : null}
          </details>

          <small className="muted">{rec.data.disclaimer}</small>
        </div>
      ) : null}
    </section>
  );
}

export function StockAnalysisPage({ initialSymbol }: { initialSymbol: string | null }) {
  const [symbol, setSymbol] = useState<string>(initialSymbol?.toUpperCase() || "SPY");
  const [range, setRange] = useState("6M");
  const [interval, setInterval] = useState("1day");
  const [kind, setKind] = useState<ChartKind>("line");
  const [overlays, setOverlays] = useState<string[]>(["sma20"]);
  const [compareWith, setCompareWith] = useState("");
  const [compareSymbols, setCompareSymbols] = useState<string[]>([]);
  const [strategyId, setStrategyId] = useState<string | null>(null);

  useEffect(() => {
    if (initialSymbol) setSymbol(initialSymbol.toUpperCase());
  }, [initialSymbol]);

  const meta = useAsync((signal) => marketMeta(signal), "meta");
  const strategies = useAsync((signal) => fetchStrategies(signal), "strategies");
  const watchlist = useAsync((signal) => fetchWatchlist(signal), "watchlist");

  const key = `${symbol}|${range}|${interval}|${overlays.join(",")}`;
  const quote = useAsync((signal) => fetchQuote(symbol, signal), symbol);
  const series = useAsync((signal) => fetchSeries(symbol, { interval, range, overlays }, signal), key);
  const stats = useAsync((signal) => fetchStats(symbol, { interval, range }, signal), `${symbol}|${range}|${interval}|s`);
  const compareKey = compareSymbols.length ? `${[symbol, ...compareSymbols].join(",")}|${range}|${interval}` : null;
  const comparison = useAsync(
    compareKey ? (signal) => fetchComparison([symbol, ...compareSymbols], { interval, range }, signal) : null,
    compareKey,
  );

  const ranges = meta.data?.ranges ?? DEFAULT_RANGES;
  const intervals = meta.data?.intervals ?? DEFAULT_INTERVALS;

  // Only offer intervals the data source can serve; fall back if the current one is not among them.
  useEffect(() => {
    if (meta.data && !meta.data.intervals.includes(interval)) {
      setInterval(meta.data.intervals[0] ?? "1day");
    }
  }, [meta.data, interval]);
  const onWatchlist = useMemo(
    () => (watchlist.data?.items ?? []).some((item) => item.asset.symbol === symbol),
    [watchlist.data, symbol],
  );
  const toggleWatch = useAction(async () => {
    if (onWatchlist) await removeFromWatchlist(symbol);
    else await addToWatchlist(symbol);
    watchlist.reload();
  });

  const pick = useCallback((next: string) => {
    setSymbol(next.toUpperCase());
    setCompareSymbols([]);
    window.location.hash = `#/analysis/${encodeURIComponent(next.toUpperCase())}`;
  }, []);

  const toggleOverlay = (name: string) =>
    setOverlays((current) => (current.includes(name) ? current.filter((n) => n !== name) : [...current, name]));

  const addCompare = (event: FormEvent) => {
    event.preventDefault();
    const next = compareWith.trim().toUpperCase();
    if (next && next !== symbol && !compareSymbols.includes(next) && compareSymbols.length < 4) {
      setCompareSymbols([...compareSymbols, next]);
    }
    setCompareWith("");
  };

  const lastQuote = quote.data;
  const change = lastQuote?.change_rate ?? null;
  const symbolMissing = series.error !== null && /not in|not found|does not exist/i.test(series.error);

  return (
    <AppShell currentPage="analysis">
      <main className="dashboard dashboard--finance" id="stock-analysis">
        <PageHeading
          kicker="ONE INSTRUMENT, IN DEPTH"
          title="Stock analysis"
          subtitle="Price, risk and evidence for a single instrument, with the reasoning shown."
          aside={<FreshnessBadge provenance={series.data?.provenance ?? lastQuote?.provenance} />}
        />

        <SymbolSearch onPick={pick} />

        <section className="panel analysis-main" aria-labelledby="chart-title">
          <div className="panel-heading panel-heading--chart">
            <div>
              <span className="section-kicker">{series.data?.asset.exchange ?? "INSTRUMENT"}</span>
              <h2 id="chart-title">
                {symbol} <span>{series.data?.asset.asset_class ? humanize(series.data.asset.asset_class) : ""}</span>
              </h2>
            </div>
            <div className="chart-controls">
              <div className="range-tabs" role="group" aria-label="Date range">
                {ranges.map((item) => (
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
              <label className="field field--compact">
                <span className="visually-hidden">Interval</span>
                <select value={interval} onChange={(event) => setInterval(event.target.value)} aria-label="Bar interval">
                  {intervals.map((item) => (
                    <option key={item} value={item}>
                      {INTERVAL_LABEL[item] ?? item}
                    </option>
                  ))}
                </select>
              </label>
              <div className="range-tabs" role="group" aria-label="Chart type">
                {(["line", "candles"] as ChartKind[]).map((item) => (
                  <button
                    key={item}
                    type="button"
                    className={item === kind ? "range-tab range-tab--active" : "range-tab"}
                    aria-pressed={item === kind}
                    onClick={() => setKind(item)}
                  >
                    {item === "line" ? "Line" : "Candles"}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="performance-metric">
            <strong>{lastQuote ? money(lastQuote.price, lastQuote.currency) : quote.loading ? "…" : "—"}</strong>
            <span className={`market-change market-change--${direction(change)}`}>{signedPercent(change)}</span>
            <small>{lastQuote ? `Quote observed ${dateTime(lastQuote.observed_at)} · ${lastQuote.source}` : quote.error ?? ""}</small>
          </div>

          <div className="overlay-toggles" role="group" aria-label="Indicators">
            {(meta.data?.overlays ?? ["sma20", "sma50"]).filter((name) => name !== "rsi14").map((name) => (
              <label className="check" key={name}>
                <input type="checkbox" checked={overlays.includes(name)} onChange={() => toggleOverlay(name)} />
                <span>{name.toUpperCase().replace("SMA", "SMA ")}</span>
              </label>
            ))}
            <button
              type="button"
              className="secondary-button"
              disabled={toggleWatch.running || watchlist.loading}
              aria-pressed={onWatchlist}
              onClick={() => void toggleWatch.run()}
            >
              {onWatchlist ? "★ On watchlist" : "☆ Add to watchlist"}
            </button>
          </div>
          {toggleWatch.error ? <Notice tone="error">{toggleWatch.error}</Notice> : null}

          <div className="chart-wrap">
            {series.loading && !series.data ? <Loading label="Loading price history…" /> : null}
            {series.error ? (
              <Notice tone="error" title={symbolMissing ? "Unknown symbol" : "Price history unavailable"} onRetry={series.reload}>
                {series.error}
              </Notice>
            ) : null}
            {series.data ? (
              series.data.bars.length >= 2 ? (
                <PriceChart
                  bars={series.data.bars}
                  overlays={series.data.overlays}
                  kind={kind}
                  currency={lastQuote?.currency ?? series.data.asset.currency ?? "USD"}
                  label={`${symbol} price`}
                />
              ) : (
                <Empty title="No history for this range">The provider returned too few bars to draw a chart.</Empty>
              )
            ) : null}
          </div>
          {series.data?.notes.map((note) => (
            <p className="source-note" key={note}>
              {note}
            </p>
          ))}
          {series.data ? (
            <p className="source-note">
              {series.data.quality.count} bars · {series.data.quality.gap_count} gap(s) · source {series.data.provenance.source}. Missing bars are never filled in.
            </p>
          ) : null}
        </section>

        <div className="dashboard-grid dashboard-grid--secondary">
          <RecommendationPanel
            symbol={symbol}
            strategyId={strategyId}
            portfolioId={null}
          />

          <aside className="stack">
            <section className="panel analysis-panel" aria-labelledby="stats-title">
              <div className="panel-heading">
                <div>
                  <span className="section-kicker">THE NUMBERS</span>
                  <h2 id="stats-title">Statistics</h2>
                </div>
              </div>
              {stats.loading && !stats.data ? <Loading /> : null}
              {stats.error ? <Notice tone="error" onRetry={stats.reload}>{stats.error}</Notice> : null}
              {stats.data ? (
                <>
                  <dl className="facts facts--stack">
                    <div><dt>Period return</dt><dd className={`market-change--${direction(stats.data.period_return)}`}>{signedPercent(stats.data.period_return)}</dd></div>
                    <div>
                      <dt>Annualised volatility</dt>
                      <dd>{percent(stats.data.annualized_volatility)}</dd>
                      <small>{stats.data.periods_per_year ? `${stats.data.periods_per_year} periods/yr` : "not annualised for this interval"}</small>
                    </div>
                    <div><dt>Max drawdown</dt><dd>{percent(stats.data.max_drawdown)}</dd></div>
                    <div><dt>Current drawdown</dt><dd>{percent(stats.data.current_drawdown)}</dd></div>
                    <div><dt>Range high / low</dt><dd>{number(stats.data.period_high)} / {number(stats.data.period_low)}</dd></div>
                    <div><dt>Average volume</dt><dd>{stats.data.average_volume === null ? "—" : number(stats.data.average_volume, 0)}</dd></div>
                    <div><dt>RSI (14)</dt><dd>{number(stats.data.rsi_14, 1)}</dd></div>
                    <div><dt>SMA 20 / 50</dt><dd>{number(stats.data.sma_20)} / {number(stats.data.sma_50)}</dd></div>
                  </dl>
                  {stats.data.notes.map((n) => (
                    <p className="source-note" key={n}>{n}</p>
                  ))}
                </>
              ) : null}
            </section>

            <section className="panel analysis-panel" aria-labelledby="compare-title">
              <div className="panel-heading">
                <div>
                  <span className="section-kicker">SIDE BY SIDE</span>
                  <h2 id="compare-title">Compare</h2>
                </div>
              </div>
              <form className="inline-form" onSubmit={addCompare}>
                <label className="field field--grow">
                  <span>Add symbol</span>
                  <input value={compareWith} onChange={(event) => setCompareWith(event.target.value)} maxLength={24} placeholder="e.g. MSFT" />
                </label>
                <button className="secondary-button" type="submit" disabled={!compareWith.trim() || compareSymbols.length >= 4}>
                  Compare
                </button>
              </form>
              {compareSymbols.length ? (
                <p className="chips">
                  {compareSymbols.map((s) => (
                    <button key={s} type="button" className="chip" onClick={() => setCompareSymbols(compareSymbols.filter((x) => x !== s))} aria-label={`Remove ${s} from comparison`}>
                      {s} ×
                    </button>
                  ))}
                </p>
              ) : null}
              {comparison.loading ? <Loading /> : null}
              {comparison.error ? <Notice tone="error" onRetry={comparison.reload}>{comparison.error}</Notice> : null}
              {comparison.data ? (
                <div className="stack">
                  <table className="table" aria-label="Comparison">
                    <thead>
                      <tr><th>Symbol</th><th>Return</th><th>Volatility</th><th>Max DD</th></tr>
                    </thead>
                    <tbody>
                      {comparison.data.series.map((s) => (
                        <tr key={s.asset.symbol}>
                          <th scope="row">{s.asset.display_symbol}</th>
                          <td className={`market-change--${direction(s.period_return)}`}>{signedPercent(s.period_return)}</td>
                          <td>{percent(s.annualized_volatility)}</td>
                          <td>{percent(s.max_drawdown)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {comparison.data.notes.map((n) => (
                    <p className="source-note" key={n}>{n}</p>
                  ))}
                </div>
              ) : null}
            </section>

            <section className="panel analysis-panel" aria-labelledby="strategy-pick-title">
              <h2 id="strategy-pick-title" className="visually-hidden">Strategy used</h2>
              <label className="field">
                <span>Evaluate with strategy</span>
                <select value={strategyId ?? ""} onChange={(event) => setStrategyId(event.target.value || null)}>
                  <option value="">Active strategy</option>
                  {(strategies.data?.strategies ?? []).map((s) => (
                    <option key={s.strategy_id} value={s.strategy_id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </label>
            </section>
          </aside>
        </div>
      </main>
    </AppShell>
  );
}
