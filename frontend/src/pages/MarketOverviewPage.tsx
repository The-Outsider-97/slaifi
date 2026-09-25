import { AppShell } from "../components/AppShell";
import { GoalsCard } from "../components/GoalsCard";
import { MarketPerformanceChart } from "../components/MarketPerformanceChart";
import { MarketSummaryCard, type SummaryMarket } from "../components/MarketSummaryCard";
import { MarketWatchTable } from "../components/MarketWatchTable";
import { SlaiInsightCard } from "../components/SlaiInsightCard";
import { SUMMARY_FALLBACKS } from "../data/demoMarket";
import { useMarketDashboard } from "../hooks/useMarketDashboard";
import type { MarketOverview } from "../types/market";

function summaryMarkets(overview: MarketOverview | null): SummaryMarket[] {
  const useApiValues = overview !== null && overview.data_mode !== "mock";
  const quotes = new Map((overview?.quotes ?? []).map((quote) => [quote.symbol.toUpperCase(), quote]));
  return SUMMARY_FALLBACKS.map((fallback) => {
    const quote = useApiValues ? quotes.get(fallback.key) : undefined;
    if (!quote) {
      return { ...fallback, sparkline: [...fallback.sparkline], source: "illustrative" as const };
    }
    return {
      key: fallback.key,
      name: fallback.name,
      value: Number(quote.price),
      changePercent: quote.change_percent === null ? fallback.changePercent : Number(quote.change_percent),
      sparkline: [...fallback.sparkline],
      source: "api" as const,
    };
  });
}

export function MarketOverviewPage() {
  const dashboard = useMarketDashboard();
  const markets = summaryMarkets(dashboard.overview);
  const dataMode = dashboard.overview?.data_mode ?? "illustrative fallback";

  return (
    <AppShell>
      <main className="dashboard" id="market-overview">
        <header className="page-heading">
          <div>
            <span className="section-kicker">YOUR MARKET, IN PERSPECTIVE</span>
            <h1>Market overview<span>.</span></h1>
            <p>A clearer view of the market. A more considered next move.</p>
          </div>
          <span className="snapshot-note">
            {dashboard.loading
              ? "Loading market snapshot"
              : `${dataMode === "mock" ? "Illustrative market snapshot" : "Market snapshot"} · USD`}
          </span>
        </header>

        {dashboard.marketError ? (
          <div className="inline-alert" role="alert">
            <strong>Market API unavailable.</strong> Displaying clearly identified illustrative fallback values.
          </div>
        ) : null}
        {dashboard.slaiError ? (
          <div className="inline-alert inline-alert--quiet" role="status">
            SLAI status could not be reached; deterministic market content remains available.
          </div>
        ) : null}

        <section className="summary-grid" aria-label="Market summary">
          {markets.map((market) => <MarketSummaryCard key={market.key} market={market} />)}
        </section>

        <div className="dashboard-grid dashboard-grid--primary">
          <MarketPerformanceChart />
          <SlaiInsightCard
            runtime={dashboard.slai}
            analysis={dashboard.analysis}
            loading={dashboard.analysisLoading}
            error={dashboard.analysisError}
            onExplore={dashboard.runInsight}
          />
        </div>

        <div className="dashboard-grid dashboard-grid--secondary">
          <MarketWatchTable />
          <GoalsCard />
        </div>

        <footer className="dashboard-footer">
          <div><strong>SLAIFI</strong><span>A little more insight. A little less noise.</span></div>
          <span>Educational demo · No trades are executed</span>
        </footer>
      </main>
    </AppShell>
  );
}
