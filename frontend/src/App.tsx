import { useEffect, useState } from "react";

import type { AppPage } from "./components/AppShell";
import { AdvisorPage } from "./pages/AdvisorPage";
import { MarketOverviewPage } from "./pages/MarketOverviewPage";
import { MyPortfolioPage } from "./pages/MyPortfolioPage";
import { PaperTradingPage } from "./pages/PaperTradingPage";
import { SettingsPage } from "./pages/SettingsPage";
import { StockAnalysisPage } from "./pages/StockAnalysisPage";
import { StrategiesGoalsPage } from "./pages/StrategiesGoalsPage";

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
