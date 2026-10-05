import { AppShell } from "../components/AppShell";
import { usePortfolioDashboard } from "../hooks/usePortfolioDashboard";
import type {
  PortfolioPosition,
  PortfolioRisk,
  SlaiRuntimeStatus,
} from "../types/market";

function formatMoney(value: string | number, currency: string) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(numeric);
  } catch {
    return numeric.toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }
}

function formatRate(value: number | null) {
  return value === null || !Number.isFinite(value) ? "—" : `${(value * 100).toFixed(2)}%`;
}

function PortfolioMetric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <article className="summary-card portfolio-summary-card">
      <span className="summary-card__name">{label}</span>
      <div className="summary-card__value-row"><strong>{value}</strong></div>
      <span className="portfolio-metric-detail">{detail}</span>
    </article>
  );
}

function HoldingsTable({ positions, currency }: { positions: PortfolioPosition[]; currency: string }) {
  return (
    <section className="panel portfolio-holdings" aria-labelledby="holdings-title">
      <div className="panel-heading">
        <div>
          <span className="section-kicker">WHAT YOU OWN</span>
          <h2 id="holdings-title">Holdings</h2>
        </div>
        <span className="snapshot-note">{positions.length} position{positions.length === 1 ? "" : "s"}</span>
      </div>

      {positions.length === 0 ? (
        <div className="data-state">This portfolio currently has no open positions.</div>
      ) : (
        <div className="holdings-table" role="table" aria-label="Portfolio holdings">
          <div className="holdings-row holdings-row--header" role="row">
            <span role="columnheader">Asset</span>
            <span role="columnheader">Quantity</span>
            <span role="columnheader">Price</span>
            <span role="columnheader">Market value</span>
            <span role="columnheader">Weight</span>
            <span role="columnheader">Unrealized P/L</span>
          </div>
          {positions.map((position) => {
            const pnl = Number(position.unrealized_pnl);
            const direction = pnl > 0 ? "positive" : pnl < 0 ? "negative" : "neutral";
            return (
              <div key={position.asset} className="holdings-row" role="row">
                <div className="watch-asset" role="cell">
                  <span className="ticker-badge">{position.asset[0] ?? "•"}</span>
                  <span>
                    <strong>{position.asset}</strong>
                    <small>Avg. {formatMoney(position.average_cost, currency)}</small>
                  </span>
                </div>
                <span role="cell">{Number(position.quantity).toLocaleString()}</span>
                <strong role="cell">{formatMoney(position.market_price, currency)}</strong>
                <strong role="cell">{formatMoney(position.market_value, currency)}</strong>
                <span role="cell">
                  {position.portfolio_weight === null ? "—" : `${(position.portfolio_weight * 100).toFixed(2)}%`}
                </span>
                <span role="cell" className={`market-change market-change--${direction}`}>
                  {formatMoney(position.unrealized_pnl, currency)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

function AllocationCard({ positions }: { positions: PortfolioPosition[] }) {
  const weighted = positions
    .filter((position) => position.portfolio_weight !== null)
    .sort((a, b) => (b.portfolio_weight ?? 0) - (a.portfolio_weight ?? 0));

  return (
    <section className="panel allocation-panel" aria-labelledby="allocation-title">
      <div className="panel-heading">
        <div>
          <span className="section-kicker">PORTFOLIO STRUCTURE</span>
          <h2 id="allocation-title">Allocation</h2>
        </div>
      </div>
      {weighted.length === 0 ? (
        <div className="data-state">Allocation data is unavailable.</div>
      ) : (
        <div className="allocation-list">
          {weighted.map((position) => {
            const weight = (position.portfolio_weight ?? 0) * 100;
            return (
              <div key={position.asset} className="allocation-item">
                <div className="allocation-item__header">
                  <strong>{position.asset}</strong><span>{weight.toFixed(2)}%</span>
                </div>
                <div className="allocation-track" aria-label={`${position.asset} ${weight.toFixed(2)}%`}>
                  <span className="allocation-fill" style={{ width: `${Math.min(100, Math.max(0, weight))}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

function RiskCard({ risk }: { risk: PortfolioRisk | null }) {
  return (
    <section className="panel portfolio-risk-panel" aria-labelledby="portfolio-risk-title">
      <div className="panel-heading">
        <div>
          <span className="section-kicker">RISK IN CONTEXT</span>
          <h2 id="portfolio-risk-title">Portfolio risk</h2>
        </div>
      </div>
      {!risk ? (
        <div className="data-state">
          Historical portfolio return data has not been supplied, so volatility, drawdown and risk-adjusted-return statistics are not being fabricated.
        </div>
      ) : (
        <div className="risk-grid">
          <div><span>Annualized volatility</span><strong>{formatRate(risk.annualized_volatility)}</strong></div>
          <div><span>Max drawdown</span><strong>{formatRate(risk.maximum_drawdown)}</strong></div>
          <div><span>Sharpe ratio</span><strong>{risk.sharpe_ratio === null ? "—" : risk.sharpe_ratio.toFixed(2)}</strong></div>
          <div><span>Concentration HHI</span><strong>{risk.concentration_hhi === null ? "—" : risk.concentration_hhi.toFixed(3)}</strong></div>
        </div>
      )}
    </section>
  );
}

function PortfolioInsight({
  reasoning,
  loading,
  error,
  onExplore,
}: {
  reasoning: SlaiRuntimeStatus | null;
  loading: boolean;
  error: string | null;
  onExplore: () => void;
}) {
  const interpretation = reasoning?.interpretation?.trim() ?? null;
  return (
    <aside className="panel insight-panel portfolio-insight" aria-labelledby="portfolio-insight-title">
      <div className="insight-header">
        <span className="insight-label">✧ SLAI PORTFOLIO INSIGHT</span>
        <span>{reasoning?.status ?? "not requested"}</span>
      </div>
      <span className="insight-spark" aria-hidden="true">✧</span>
      <span className="section-kicker">YOUR PORTFOLIO, IN CONTEXT</span>
      <h2 id="portfolio-insight-title">
        {interpretation ? "What stands out." : "Reasoning on demand."}
      </h2>
      <p className={interpretation ? "insight-copy insight-copy--live" : "insight-copy"}>
        {interpretation ?? "Portfolio valuation loads deterministically. Request SLAI only when you want a contextual interpretation."}
      </p>
      {reasoning ? (
        <div className="insight-meta">
          <div><span>Agent</span><strong>{reasoning.agent ?? "Not reported"}</strong></div>
          <div>
            <span>Confidence</span>
            <strong>{reasoning.confidence == null ? "Not reported" : `${(reasoning.confidence * 100).toFixed(0)}%`}</strong>
          </div>
          <div><span>Validation</span><strong>{reasoning.validation_status ?? "Not reported"}</strong></div>
        </div>
      ) : null}
      {error ? <p className="insight-error" role="alert">{error}</p> : null}
      <button className="primary-cta" type="button" disabled={loading} onClick={onExplore}>
        <span>{loading ? "Reasoning…" : reasoning ? "Refresh reasoning" : "Explore the reasoning"}</span>
        <span aria-hidden="true">↗</span>
      </button>
    </aside>
  );
}

function PageHeading() {
  return (
    <header className="page-heading">
      <div>
        <span className="section-kicker">YOUR PORTFOLIO, IN CONTEXT</span>
        <h1>My portfolio<span>.</span></h1>
        <p>Understand what you own. See what drives the risk.</p>
      </div>
    </header>
  );
}

export function MyPortfolioPage() {
  const dashboard = usePortfolioDashboard();

  if (dashboard.loading) {
    return (
      <AppShell currentPage="portfolio">
        <main className="dashboard"><PageHeading /><div className="data-state portfolio-page-state">Loading portfolio…</div></main>
      </AppShell>
    );
  }

  if (dashboard.error) {
    return (
      <AppShell currentPage="portfolio">
        <main className="dashboard">
          <PageHeading />
          <div className="inline-alert" role="alert">
            <strong>Portfolio unavailable.</strong> {dashboard.error}
            <button type="button" className="secondary-button" onClick={dashboard.refresh}>Retry</button>
          </div>
        </main>
      </AppShell>
    );
  }

  if (!dashboard.portfolio) {
    return (
      <AppShell currentPage="portfolio">
        <main className="dashboard">
          <PageHeading />
          <section className="panel portfolio-empty-state">
            <span className="insight-spark" aria-hidden="true">✧</span>
            <span className="section-kicker">NO PORTFOLIO CONNECTED</span>
            <h2>Your portfolio is empty.</h2>
            <p>SLAIFI has no current portfolio ledger to analyse. No holdings, values or returns have been invented.</p>
          </section>
        </main>
      </AppShell>
    );
  }

  const { snapshot, risk, reasoning } = dashboard.portfolio;
  const currency = snapshot.base_currency;

  return (
    <AppShell currentPage="portfolio">
      <main className="dashboard" id="portfolio">
        <header className="page-heading">
          <div>
            <span className="section-kicker">YOUR PORTFOLIO, IN CONTEXT</span>
            <h1>My portfolio<span>.</span></h1>
            <p>Understand what you own. See what drives the risk.</p>
          </div>
          <span className="snapshot-note">Valued {new Date(snapshot.as_of).toLocaleString()} · {currency}</span>
        </header>

        <section className="summary-grid" aria-label="Portfolio summary">
          <PortfolioMetric label="Portfolio value" value={formatMoney(snapshot.total_value, currency)} detail="Current valuation" />
          <PortfolioMetric label="Invested assets" value={formatMoney(snapshot.securities_market_value, currency)} detail="Securities market value" />
          <PortfolioMetric label="Cash balance" value={formatMoney(snapshot.cash_balance, currency)} detail="Portfolio cash" />
          <PortfolioMetric label="Open positions" value={String(snapshot.positions.length)} detail="Current holdings" />
        </section>

        <div className="dashboard-grid dashboard-grid--primary">
          <section className="panel performance-panel" aria-labelledby="portfolio-performance-title">
            <div className="panel-heading">
              <div>
                <span className="section-kicker">PORTFOLIO PERFORMANCE</span>
                <h2 id="portfolio-performance-title">Historical performance</h2>
              </div>
            </div>
            <div className="data-state">
              Historical portfolio valuation series is not available from the current backend contract. No fake performance chart is shown.
            </div>
          </section>
          <PortfolioInsight
            reasoning={reasoning}
            loading={dashboard.insightLoading}
            error={dashboard.insightError}
            onExplore={dashboard.requestInsight}
          />
        </div>

        <div className="dashboard-grid dashboard-grid--secondary">
          <HoldingsTable positions={snapshot.positions} currency={currency} />
          <AllocationCard positions={snapshot.positions} />
        </div>

        <RiskCard risk={risk} />

        <footer className="dashboard-footer">
          <div><strong>SLAIFI</strong><span>Portfolio intelligence grounded in your actual holdings.</span></div>
          <span>No trades are executed</span>
        </footer>
      </main>
    </AppShell>
  );
}
