import { Suspense, lazy, useEffect, useState } from "react";

import type { AppPage } from "./components/AppShell";
import { MarketOverviewPage } from "./pages/MarketOverviewPage";

// The first page loads with the app; every other page is fetched the first time it is opened, so
// opening SLAIFI does not download code for screens the person may never visit.
const AdvisorPage = lazy(() => import("./pages/AdvisorPage").then((m) => ({ default: m.AdvisorPage })));
const MyPortfolioPage = lazy(() => import("./pages/MyPortfolioPage").then((m) => ({ default: m.MyPortfolioPage })));
const PaperTradingPage = lazy(() => import("./pages/PaperTradingPage").then((m) => ({ default: m.PaperTradingPage })));
const SettingsPage = lazy(() => import("./pages/SettingsPage").then((m) => ({ default: m.SettingsPage })));
const StockAnalysisPage = lazy(() => import("./pages/StockAnalysisPage").then((m) => ({ default: m.StockAnalysisPage })));
const StrategiesGoalsPage = lazy(() => import("./pages/StrategiesGoalsPage").then((m) => ({ default: m.StrategiesGoalsPage })));

const ROUTES: Record<string, AppPage> = {
  market: "market",
  analysis: "analysis",
  portfolio: "portfolio",
  paper: "paper",
  advisor: "advisor",
  strategy: "strategy",
  settings: "settings",
};

/** ``#/analysis/AAPL`` → page ``analysis``; the rest of the path belongs to the page. */
export function routeFromHash(hash: string): { page: AppPage; param: string | null } {
  const parts = hash.replace(/^#\/?/, "").split("/");
  const page = ROUTES[parts[0]?.toLowerCase() ?? ""] ?? "market";
  const rest = parts.slice(1).join("/");
  return { page, param: rest ? decodeURIComponent(rest) : null };
}

export default function App() {
  const [route, setRoute] = useState(() => routeFromHash(window.location.hash));

  useEffect(() => {
    const onHashChange = () => setRoute(routeFromHash(window.location.hash));
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  return (
    <Suspense fallback={<div className="data-state" role="status">Loading…</div>}>
      <Routed route={route} />
    </Suspense>
  );
}

function Routed({ route }: { route: { page: AppPage; param: string | null } }) {
  switch (route.page) {
    case "analysis":
      return <StockAnalysisPage initialSymbol={route.param} />;
    case "portfolio":
      return <MyPortfolioPage />;
    case "paper":
      return <PaperTradingPage />;
    case "advisor":
      return <AdvisorPage />;
    case "strategy":
      return <StrategiesGoalsPage />;
    case "settings":
      return <SettingsPage />;
    default:
      return <MarketOverviewPage />;
  }
}
