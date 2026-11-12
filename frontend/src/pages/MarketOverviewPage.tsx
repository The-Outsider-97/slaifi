import {
  AppShell,
} from "../components/AppShell";
import {
  GoalsCard,
} from "../components/GoalsCard";
import {
  MarketPerformanceChart,
} from "../components/MarketPerformanceChart";
import {
  MarketSummaryCard,
  type SummaryMarket,
} from "../components/MarketSummaryCard";
import {
  MarketWatchTable,
} from "../components/MarketWatchTable";
import {
  SlaiInsightCard,
} from "../components/SlaiInsightCard";
import {
  useMarketDashboard,
} from "../hooks/useMarketDashboard";

const MARKET_NAMES:
  Record<string, string> = {
    SPY: "S&P 500 ETF",
    QQQ: "NASDAQ-100 ETF",
    DIA: "DOW JONES ETF",
    VIX: "VIX",
    SPX: "S&P 500",
    "^GSPC": "S&P 500",
    IXIC: "NASDAQ",
    "^IXIC": "NASDAQ",
    DJI: "DOW JONES",
    "^DJI": "DOW JONES",
    "^VIX": "VIX",
  };

export function MarketOverviewPage() {
  const dashboard =
    useMarketDashboard();

  const primarySymbol =
    dashboard.overview?.quotes[0]
      ?.symbol ?? null;

  const primarySparkline =
    dashboard.history?.bars.map(
      (bar) => Number(bar.close),
    ) ?? [];

  const nameOf = (symbol: string) =>
    MARKET_NAMES[symbol.toUpperCase()] ??
    symbol;

  const markets: SummaryMarket[] = [
    ...(
      dashboard.overview?.quotes ?? []
    ).map((quote) => ({
      key: quote.symbol,
      name: nameOf(quote.symbol),
      value: Number(quote.price),
      changePercent:
        quote.change_percent === null
          ? null
          : Number(
              quote.change_percent,
            ),
      sparkline:
        quote.symbol === primarySymbol
          ? primarySparkline
          : [],
      source: quote.source,
      observedAt: quote.observed_at,
      lastKnown: quote.last_known,
    })),
    ...(
      dashboard.overview
        ?.unavailable ?? []
    ).map((symbol) => ({
      key: symbol,
      name: nameOf(symbol),
      value: null,
      changePercent: null,
      sparkline: [],
      source: null,
      observedAt: null,
      lastKnown: false,
    })),
  ];

  const mode =
    dashboard.overview?.data_mode ??
    null;

  const snapshotLabel =
    mode === "live"
      ? "Live snapshot"
      : mode === "delayed"
        ? "Delayed snapshot"
        : mode === "live_delay_unknown"
          ? "Provider snapshot · delay unknown"
          : mode === "last_known"
            ? "Last known data"
            : "NOT AVAILABLE";

  const currency =
    dashboard.overview?.quotes[0]
      ?.currency ?? "—";

  return (
    <AppShell currentPage="market">
      <main
        className="dashboard"
        id="market-overview"
      >
        <header className="page-heading">
          <div>
            <span className="section-kicker">
              YOUR MARKET, IN
              PERSPECTIVE
            </span>

            <h1>
              Market overview
              <span>.</span>
            </h1>

            <p>
              A clearer view of the
              market. A more considered
              next move.
            </p>
          </div>

          <span
            className="snapshot-note"
            data-testid="snapshot-note"
          >
            {dashboard.loading
              ? "Loading market snapshot"
              : dashboard.overview
                ? mode === "unavailable"
                  ? snapshotLabel
                  : `${snapshotLabel} · ${currency}`
                : "NOT AVAILABLE"}
          </span>
        </header>

        {mode === "last_known" ? (
          <div
            className="inline-alert"
            role="status"
            data-testid="last-known-banner"
          >
            <strong>
              Showing last known data.
            </strong>{" "}
            No market-data source could
            be reached, so these are the
            most recent real quotes
            SLAIFI saved. Each shows
            when it was observed.
          </div>
        ) : null}

        {mode === "unavailable" &&
        !dashboard.marketError ? (
          <div
            className="inline-alert"
            role="alert"
            data-testid="unavailable-banner"
          >
            <strong>
              NOT AVAILABLE.
            </strong>{" "}
            No live quotes could be
            retrieved and nothing has
            been saved yet. Add at least
            one free API key (see
            Settings → Market data) and
            reload. SLAIFI never shows
            invented prices.
          </div>
        ) : null}

        {dashboard.marketError ? (
          <div
            className="inline-alert"
            role="alert"
          >
            <strong>
              NOT AVAILABLE.
            </strong>{" "}
            {dashboard.marketError}
          </div>
        ) : null}

        {dashboard.slaiError ? (
          <div
            className="inline-alert inline-alert--quiet"
            role="status"
          >
            SLAI reasoning is unavailable.
            Market data remains usable.
          </div>
        ) : null}

        {dashboard.loading ? (
          <section
            className="summary-grid"
            aria-label="Loading market summary"
          >
            {Array.from(
              { length: 4 },
              (_, index) => (
                <div
                  key={index}
                  className="summary-card summary-card--loading"
                />
              ),
            )}
          </section>
        ) : markets.length > 0 ? (
          <section
            className="summary-grid"
            aria-label="Market summary"
          >
            {markets.map(
              (market) => (
                <MarketSummaryCard
                  key={market.key}
                  market={market}
                />
              ),
            )}
          </section>
        ) : !dashboard.marketError ? (
          <div className="data-state">
            NOT AVAILABLE
          </div>
        ) : null}

        <div className="dashboard-grid dashboard-grid--primary">
          <MarketPerformanceChart
            history={
              dashboard.history
            }
            range={dashboard.range}
            onRangeChange={
              dashboard.setRange
            }
            loading={
              dashboard.historyLoading
            }
            error={
              dashboard.historyError
            }
          />

          <SlaiInsightCard
            runtime={dashboard.slai}
            analysis={
              dashboard.analysis
            }
            loading={
              dashboard.analysisLoading
            }
            error={
              dashboard.analysisError
            }
            hasEvidence={
              dashboard.hasAnalysisEvidence
            }
            onExplore={
              dashboard.runInsight
            }
          />
        </div>

        <div className="dashboard-grid dashboard-grid--secondary">
          <MarketWatchTable
            quotes={
              dashboard.overview
                ?.quotes ?? []
            }
            unavailable={
              dashboard.overview
                ?.unavailable ?? []
            }
            loading={
              dashboard.loading
            }
          />

          <GoalsCard />
        </div>

        <footer className="dashboard-footer">
          <div>
            <strong>
              SLAIFI
            </strong>
            <span>
              A little more insight. A
              little less noise.
            </span>
          </div>

          <span>
            Financial intelligence · No
            trades are executed
          </span>
        </footer>
      </main>
    </AppShell>
  );
}
