import {
  useEffect,
  useState,
} from "react";

import {
  MarketOverviewPage,
} from "./pages/MarketOverviewPage";
import {
  MyPortfolioPage,
} from "./pages/MyPortfolioPage";

type AppPage =
  | "market"
  | "portfolio";

function pageFromHash(): AppPage {
  const hash =
    window.location.hash
      .toLowerCase();

  if (
    hash === "#/portfolio" ||
    hash.startsWith(
      "#/portfolio/",
    )
  ) {
    return "portfolio";
  }

  return "market";
}

export default function App() {
  const [
    page,
    setPage,
  ] = useState<AppPage>(
    pageFromHash,
  );

  useEffect(() => {
    const onHashChange = () => {
      setPage(
        pageFromHash(),
      );
    };

    window.addEventListener(
      "hashchange",
      onHashChange,
    );

    return () =>
      window.removeEventListener(
        "hashchange",
        onHashChange,
      );
  }, []);

  if (page === "portfolio") {
    return <MyPortfolioPage />;
  }

  return <MarketOverviewPage />;
}
