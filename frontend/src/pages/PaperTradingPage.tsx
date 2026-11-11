import { useEffect, useMemo, useState, type FormEvent } from "react";

import { AppShell } from "../components/AppShell";
import { Explained } from "../components/finance/Explained";
import { FreshnessBadge } from "../components/finance/FreshnessBadge";
import { Empty, Loading, Notice, Simulated } from "../components/finance/Notice";
import { OrderTicket } from "../components/finance/OrderTicket";
import { PageHeading } from "../components/finance/PageHeading";
import { useAction, useAsync } from "../hooks/useAsync";
import { dateTime, direction, humanize, money, number, percent, quantity, signedPercent } from "../lib/format";
import {
  createPortfolio,
  depositCash,
  fetchGuidance,
  fetchPerformance,
  fetchPortfolio,
  fetchStrategies,
  fetchTradeHistory,
  listPortfolios,
  placeOrder,
  reconcilePortfolio,
  resetPortfolio,
  setPortfolioStrategy,
  withdrawCash,
} from "../services/finance";
import type { PerformanceResponse, PortfolioView } from "../types/finance";

const STORAGE_KEY = "slaifi-paper-portfolio";

function remembered(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function remember(id: string) {
  try {
    localStorage.setItem(STORAGE_KEY, id);
  } catch {
    /* a private window may refuse storage; the page works without it */
  }
}

function CreatePortfolio({ onCreated, first }: { onCreated: (id: string) => void; first: boolean }) {
  const [name, setName] = useState("Practice portfolio");
  const [capital, setCapital] = useState("10000");
  const create = useAction(createPortfolio);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const view = await create.run({ name: name.trim(), starting_capital: capital.trim() });
    if (view) onCreated(view.portfolio.portfolio_id);
  };

  return (
    <section className="panel analysis-panel" aria-labelledby="create-title">
      <div className="panel-heading">
        <div>
          <span className="section-kicker">{first ? "START HERE" : "ANOTHER ONE"}</span>
          <h2 id="create-title">{first ? "Create a paper portfolio" : "New paper portfolio"}</h2>
        </div>
        <Simulated />
      </div>
      <p className="lead">
        A paper portfolio uses simulated money to practise a strategy against real prices. No real money, account or broker is ever involved.
      </p>
      <form className="form-grid" onSubmit={submit}>
        <label className="field">
          <span>Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} required />
        </label>
        <label className="field">
          <span>Starting cash (USD)</span>
          <input inputMode="decimal" value={capital} onChange={(e) => setCapital(e.target.value)} required />
        </label>
        <button className="primary-cta primary-cta--inline" type="submit" disabled={create.running || !name.trim() || !(Number(capital) > 0)}>
          {create.running ? "Creating…" : "Create portfolio"}
        </button>
      </form>
      {create.error ? <Notice tone="error">{create.error}</Notice> : null}
    </section>
  );
}

function Summary({ view }: { view: PortfolioView }) {
  const cards = [
    { label: "Total value", value: money(view.total_value, view.currency), detail: `As of ${dateTime(view.as_of)}` },
    { label: "Cash", value: money(view.cash_balance, view.currency), detail: view.cash_weight === null ? "—" : `${percent(view.cash_weight, 1)} of portfolio` },
    { label: "Invested", value: money(view.invested_value, view.currency), detail: `${view.positions.length} position${view.positions.length === 1 ? "" : "s"}` },
    {
      label: "Profit / loss",
      value: money(view.total_pnl, view.currency),
      detail: `${signedPercent(view.simple_return)} on ${money(view.net_contributions, view.currency)} contributed`,
    },
  ];
  return (
    <div className="summary-grid" aria-label="Portfolio summary">
      {cards.map((card) => (
        <article key={card.label} className="summary-card portfolio-summary-card">
          <span className="summary-card__name">{card.label}</span>
          <div className="summary-card__value-row"><strong>{card.value}</strong></div>
          <span className="portfolio-metric-detail">{card.detail}</span>
        </article>
      ))}
    </div>
  );
}

function Positions({ view, onClose, closing }: { view: PortfolioView; onClose: (symbol: string) => void; closing: boolean }) {
  return (
    <section className="panel portfolio-holdings" aria-labelledby="pos-title">
      <div className="panel-heading">
        <div>
          <span className="section-kicker">WHAT THIS PORTFOLIO HOLDS</span>
          <h2 id="pos-title">Positions</h2>
        </div>
        <Simulated />
      </div>
      {view.warnings.map((w) => (
        <Notice key={w} tone="warning">{w}</Notice>
      ))}
      {view.positions.length === 0 ? (
        <Empty title="No open positions">Preview an order to buy something with the simulated cash.</Empty>
      ) : (
        <div className="holdings-table" role="table" aria-label="Paper positions">
          <div className="holdings-row holdings-row--header" role="row">
            <span role="columnheader">Asset</span>
            <span role="columnheader">Quantity</span>
            <span role="columnheader">Price</span>
            <span role="columnheader">Market value</span>
            <span role="columnheader">Weight</span>
            <span role="columnheader">Unrealised P/L</span>
            <span role="columnheader"><span className="visually-hidden">Actions</span></span>
          </div>
          {view.positions.map((p) => (
            <div className="holdings-row holdings-row--actions" role="row" key={p.asset.symbol}>
              <div className="watch-asset" role="cell">
                <span className="ticker-badge">{p.asset.symbol[0]}</span>
                <span>
                  <strong>{p.asset.display_symbol}</strong>
                  <small>Avg. {money(p.average_cost, view.currency)}</small>
                </span>
              </div>
              <span role="cell">{quantity(p.quantity)}</span>
              <span role="cell">
                <strong>{money(p.market_price, view.currency)}</strong>
                <small className="block">
                  {p.price_basis === "quote" ? "latest quote" : p.price_basis === "last_fill" ? "last fill (no quote)" : humanize(p.price_basis)}
                  {p.stale_price ? " · stale" : ""}
                </small>
              </span>
              <strong role="cell">{money(p.market_value, view.currency)}</strong>
              <span role="cell">{percent(p.weight, 1)}</span>
              <span role="cell" className={`market-change market-change--${direction(p.unrealized_pnl)}`}>{money(p.unrealized_pnl, view.currency)}</span>
              <span role="cell">
                <button type="button" className="secondary-button secondary-button--tight" disabled={closing} onClick={() => onClose(p.asset.symbol)} aria-label={`Close ${p.asset.symbol} position`}>
                  Close
                </button>
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function Cash({ view, onDone }: { view: PortfolioView; onDone: () => void }) {
  const [amount, setAmount] = useState("");
  const deposit = useAction(depositCash);
  const withdraw = useAction(withdrawCash);
  const id = view.portfolio.portfolio_id;

  const go = (kind: "deposit" | "withdraw") => async (event: FormEvent) => {
    event.preventDefault();
    const done = kind === "deposit" ? await deposit.run(id, amount.trim()) : await withdraw.run(id, amount.trim());
    if (done) {
      setAmount("");
      onDone();
    }
  };
  const busy = deposit.running || withdraw.running;

  return (
    <section className="panel analysis-panel" aria-labelledby="cash-title">
      <div className="panel-heading">
        <div>
          <span className="section-kicker">SIMULATED CASH</span>
          <h2 id="cash-title">Deposit or withdraw</h2>
        </div>
      </div>
      <form className="inline-form" onSubmit={go("deposit")}>
        <label className="field field--grow">
          <span>Amount ({view.currency})</span>
          <input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="1000.00" />
        </label>
        <button className="secondary-button" type="submit" disabled={busy || !(Number(amount) > 0)}>Deposit</button>
        <button className="secondary-button" type="button" disabled={busy || !(Number(amount) > 0)} onClick={go("withdraw")}>Withdraw</button>
      </form>
      {deposit.error ? <Notice tone="error">{deposit.error}</Notice> : null}
      {withdraw.error ? <Notice tone="error">{withdraw.error}</Notice> : null}
    </section>
  );
}

function EquityCurve({ perf }: { perf: PerformanceResponse }) {
  const values = perf.equity_curve.map((p) => Number(p.value));
  if (values.length < 2) return <p className="muted">The equity curve appears after a second valuation point is recorded.</p>;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * 600},${120 - ((v - min) / span) * 110 - 5}`).join(" ");
  return (
    <svg className="performance-chart" viewBox="0 0 600 120" role="img" aria-label={`Equity curve from ${money(values[0])} to ${money(values[values.length - 1])}`}>
      <polyline className="chart-line" points={pts} fill="none" />
    </svg>
  );
}

function Performance({ id, refreshKey }: { id: string; refreshKey: number }) {
  const perf = useAsync((signal) => fetchPerformance(id, signal), `${id}|${refreshKey}`);
  return (
    <section className="panel analysis-panel" aria-labelledby="perf-title">
      <div className="panel-heading">
        <div>
          <span className="section-kicker">HOW IT HAS DONE</span>
          <h2 id="perf-title">Performance</h2>
        </div>
      </div>
      {perf.loading && !perf.data ? <Loading /> : null}
      {perf.error ? <Notice tone="error" onRetry={perf.reload}>{perf.error}</Notice> : null}
      {perf.data ? (
        <div className="stack">
          <EquityCurve perf={perf.data} />
          <dl className="facts">
            <div><dt>Time-weighted return</dt><dd>{signedPercent(perf.data.time_weighted_return)}</dd><small>cash flows removed</small></div>
            <div><dt>Annualised</dt><dd>{signedPercent(perf.data.annualized_return)}</dd><small>{perf.data.annualized_return === null ? "needs a longer history" : ""}</small></div>
            <div><dt>Max drawdown</dt><dd>{percent(perf.data.max_drawdown)}</dd></div>
            <div><dt>Fees + slippage</dt><dd>{money(Number(perf.data.fees_paid) + Number(perf.data.slippage_cost))}</dd></div>
            <div><dt>Realised P/L</dt><dd>{money(perf.data.realized_pnl)}</dd></div>
            <div><dt>Unrealised P/L</dt><dd>{money(perf.data.unrealized_pnl)}</dd></div>
            <div><dt>Largest position</dt><dd>{percent(perf.data.largest_position_weight, 1)}</dd></div>
            <div><dt>Concentration (HHI)</dt><dd>{number(perf.data.concentration_hhi, 2)}</dd></div>
          </dl>
          {perf.data.notes.map((n) => (
            <p className="source-note" key={n}>{n}</p>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function History({ id, refreshKey }: { id: string; refreshKey: number }) {
  const history = useAsync((signal) => fetchTradeHistory(id, signal), `${id}|${refreshKey}`);
  return (
    <section className="panel analysis-panel" aria-labelledby="hist-title">
      <div className="panel-heading">
        <div>
          <span className="section-kicker">EVERYTHING RECORDED</span>
          <h2 id="hist-title">History</h2>
        </div>
      </div>
      {history.loading && !history.data ? <Loading /> : null}
      {history.error ? <Notice tone="error" onRetry={history.reload}>{history.error}</Notice> : null}
      {history.data && history.data.entries.length === 0 ? <Empty title="Nothing yet" /> : null}
      {history.data && history.data.entries.length ? (
        <ol className="timeline" aria-label="Portfolio history">
          {history.data.entries.map((entry, i) => (
            <li key={`${entry.at}-${i}`}>
              <time dateTime={entry.at}>{dateTime(entry.at)}</time>
              <span><strong>{humanize(entry.kind)}</strong> · {entry.summary}</span>
            </li>
          ))}
        </ol>
      ) : null}
    </section>
  );
}

function Guidance({ id, refreshKey }: { id: string; refreshKey: number }) {
  const [explain, setExplain] = useState(false);
  const guidance = useAsync((signal) => fetchGuidance(id, explain, signal), `${id}|${refreshKey}|${explain}`);
  return (
    <section className="panel analysis-panel" aria-labelledby="guide-title">
      <div className="panel-heading">
        <div>
          <span className="section-kicker">ALIGNMENT WITH YOUR STRATEGY</span>
          <h2 id="guide-title">Portfolio guidance</h2>
        </div>
        {guidance.data ? (
          <span className={`status-badge ${guidance.data.aligned ? "status-badge--dca" : "status-badge--review-risk"}`}>
            {guidance.data.aligned ? "WITHIN LIMITS" : "NEEDS ATTENTION"}
          </span>
        ) : null}
      </div>
      {guidance.loading && !guidance.data ? <Loading label="Checking the portfolio against the strategy…" /> : null}
      {guidance.error ? <Notice tone="error" onRetry={guidance.reload}>{guidance.error}</Notice> : null}
      {guidance.data ? (
        <div className="stack">
          <p className="muted">Measured against “{guidance.data.strategy.name}”.</p>
          <ul className="guidance-list">
            {guidance.data.items.map((item) => (
              <li key={item.title + item.detail} className={`guidance guidance--${item.severity}`}>
                <strong>{item.title}</strong>
                <span>{item.detail}</span>
                {item.suggestion ? <small>Suggestion: {item.suggestion}</small> : null}
              </li>
            ))}
          </ul>
          {guidance.data.holdings.length ? (
            <table className="table" aria-label="Holding assessments">
              <thead><tr><th>Holding</th><th>Assessment</th><th>Notes</th></tr></thead>
              <tbody>
                {guidance.data.holdings.map((h) => (
                  <tr key={h.symbol}>
                    <th scope="row">{h.symbol}</th>
                    <td>{h.action ?? "Insufficient evidence"}</td>
                    <td>{h.summary}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          {guidance.data.goals.map((g) => (
            <p key={g.goal_id} className="muted">
              Goal “{g.name}”: {humanize(g.status)}
              {g.required_annual_return_rate === null ? "" : `, needs about ${percent(g.required_annual_return_rate, 1)} a year`}.
              {g.findings.length ? ` ${g.findings.join(" ")}` : ""}
            </p>
          ))}
          {guidance.data.data_notes.map((n) => (
            <p className="source-note" key={n}>{n}</p>
          ))}
          <label className="check">
            <input type="checkbox" checked={explain} onChange={(e) => setExplain(e.target.checked)} />
            <span>Ask SLAI to explain</span>
          </label>
          <Explained explanation={guidance.data.explanation} />
          <small className="muted">{guidance.data.disclaimer}</small>
        </div>
      ) : null}
    </section>
  );
}

function Maintenance({ view, onChanged }: { view: PortfolioView; onChanged: () => void }) {
  const id = view.portfolio.portfolio_id;
  const [confirming, setConfirming] = useState(false);
  const [typed, setTyped] = useState("");
  const reset = useAction(resetPortfolio);
  const reconcile = useAction(reconcilePortfolio);
  const strategies = useAsync((signal) => fetchStrategies(signal), "strategies");
  const assign = useAction(setPortfolioStrategy);

  const doReset = async () => {
    const done = await reset.run(id, true);
    if (done) {
      setConfirming(false);
      setTyped("");
      onChanged();
    }
  };

  return (
    <section className="panel analysis-panel" aria-labelledby="maint-title">
      <div className="panel-heading">
        <div>
          <span className="section-kicker">LEDGER</span>
          <h2 id="maint-title">Strategy, checks and reset</h2>
        </div>
      </div>
      <div className="stack">
        <label className="field">
          <span>Strategy this portfolio is measured against</span>
          <select
            value={view.portfolio.strategy_id ?? ""}
            onChange={async (e) => {
              await assign.run(id, e.target.value || null);
              onChanged();
            }}
          >
            <option value="">Active strategy</option>
            {(strategies.data?.strategies ?? []).map((s) => (
              <option key={s.strategy_id} value={s.strategy_id}>{s.name}</option>
            ))}
          </select>
        </label>
        {assign.error ? <Notice tone="error">{assign.error}</Notice> : null}

        <div className="inline-form">
          <button type="button" className="secondary-button" disabled={reconcile.running} onClick={() => void reconcile.run(id)}>
            {reconcile.running ? "Checking…" : "Reconcile ledger"}
          </button>
          {reconcile.result ? (
            <span className={reconcile.result.consistent ? "positive-text" : "negative-text"} role="status">
              {reconcile.result.consistent
                ? `Consistent: ${reconcile.result.trade_count} trades and ${reconcile.result.cash_flow_count} cash flows agree with the balance.`
                : `${reconcile.result.issues.length} issue(s) found: ${reconcile.result.issues.map((i) => i.message).join(" ")}`}
            </span>
          ) : null}
        </div>
        {reconcile.error ? <Notice tone="error">{reconcile.error}</Notice> : null}

        {!confirming ? (
          <button type="button" className="secondary-button secondary-button--danger" onClick={() => setConfirming(true)}>
            Reset this portfolio…
          </button>
        ) : (
          <div className="danger-box" role="group" aria-label="Confirm reset">
            <p>
              Resetting erases every position, trade and cash movement and restores {money(view.portfolio.starting_capital, view.currency)} in cash. The audit
              log keeps a record that it happened. Type <strong>{view.portfolio.name}</strong> to confirm.
            </p>
            <input aria-label="Type the portfolio name to confirm" value={typed} onChange={(e) => setTyped(e.target.value)} />
            <div>
              <button type="button" className="secondary-button" onClick={() => { setConfirming(false); setTyped(""); }}>Cancel</button>
              <button type="button" className="secondary-button secondary-button--danger" disabled={typed.trim() !== view.portfolio.name || reset.running} onClick={() => void doReset()}>
                {reset.running ? "Resetting…" : "Reset portfolio"}
              </button>
            </div>
          </div>
        )}
        {reset.error ? <Notice tone="error">{reset.error}</Notice> : null}
      </div>
    </section>
  );
}

export function PaperTradingPage() {
  const [selected, setSelected] = useState<string | null>(remembered);
  const [version, setVersion] = useState(0);
  const [creating, setCreating] = useState(false);

  const list = useAsync((signal) => listPortfolios(signal), `list|${version}`);
  const ids = useMemo(() => (list.data?.portfolios ?? []).map((p) => p.portfolio_id), [list.data]);

  useEffect(() => {
    if (!list.data) return;
    if (ids.length === 0) setSelected(null);
    else if (!selected || !ids.includes(selected)) setSelected(ids[0]);
  }, [list.data, ids, selected]);

  const view = useAsync(selected ? (signal) => fetchPortfolio(selected, signal) : null, selected ? `${selected}|${version}` : null);
  const closePosition = useAction(placeOrder);

  const refresh = () => setVersion((v) => v + 1);
  const choose = (id: string) => {
    setSelected(id);
    remember(id);
  };

  const close = async (symbol: string) => {
    if (!selected) return;
    const done = await closePosition.run(selected, { symbol, side: "sell", close_position: true });
    if (done) refresh();
  };

  const portfolios = list.data?.portfolios ?? [];

  return (
    <AppShell currentPage="paper">
      <main className="dashboard dashboard--finance" id="paper-trading">
        <PageHeading
          kicker="PRACTISE WITHOUT RISK"
          title="Paper trading"
          subtitle="Simulated money, real prices, a complete record. Nothing here is a real trade."
          aside={
            <span className="simulated-banner">
              <Simulated /> No real money
            </span>
          }
        />

        {list.loading && !list.data ? <Loading label="Loading paper portfolios…" /> : null}
        {list.error ? <Notice tone="error" title="Paper portfolios unavailable" onRetry={list.reload}>{list.error}</Notice> : null}

        {list.data && portfolios.length === 0 ? <CreatePortfolio first onCreated={(id) => { choose(id); refresh(); }} /> : null}

        {portfolios.length > 0 ? (
          <>
            <div className="toolbar">
              <label className="field field--compact">
                <span>Portfolio</span>
                <select value={selected ?? ""} onChange={(e) => choose(e.target.value)} aria-label="Select paper portfolio">
                  {portfolios.map((p) => (
                    <option key={p.portfolio_id} value={p.portfolio_id}>{p.name}</option>
                  ))}
                </select>
              </label>
              <button type="button" className="secondary-button" onClick={() => setCreating((v) => !v)} aria-expanded={creating}>
                {creating ? "Hide" : "New portfolio"}
              </button>
              {view.data ? <FreshnessBadge provenance={view.data.positions[0]?.price_provenance} /> : null}
            </div>

            {creating ? <CreatePortfolio first={false} onCreated={(id) => { choose(id); setCreating(false); refresh(); }} /> : null}

            {view.loading && !view.data ? <Loading label="Valuing the portfolio…" /> : null}
            {view.error ? <Notice tone="error" title="Portfolio unavailable" onRetry={view.reload}>{view.error}</Notice> : null}
            {closePosition.error ? <Notice tone="error">{closePosition.error}</Notice> : null}
            {closePosition.result?.decision.status === "rejected" ? (
              <Notice tone="error" title="The position was not closed">
                {closePosition.result.decision.rejections.map((r) => r.message).join(" ")}
              </Notice>
            ) : null}

            {view.data ? (
              <>
                <Summary view={view.data} />
                <div className="dashboard-grid dashboard-grid--primary">
                  <Positions view={view.data} onClose={(s) => void close(s)} closing={closePosition.running} />
                  <OrderTicket portfolio={view.data} onFilled={refresh} />
                </div>
                <div className="dashboard-grid dashboard-grid--secondary">
                  <Performance id={view.data.portfolio.portfolio_id} refreshKey={version} />
                  <Cash view={view.data} onDone={refresh} />
                </div>
                <div className="dashboard-grid dashboard-grid--secondary">
                  <Guidance id={view.data.portfolio.portfolio_id} refreshKey={version} />
                  <History id={view.data.portfolio.portfolio_id} refreshKey={version} />
                </div>
                <Maintenance view={view.data} onChanged={refresh} />
              </>
            ) : null}
          </>
        ) : null}
      </main>
    </AppShell>
  );
}
