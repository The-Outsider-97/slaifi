import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MarketOverviewPage } from "./MarketOverviewPage";

const liveOverview = {
  generated_at: "2026-10-05T12:00:00+00:00",
  data_mode: "live",
  unavailable: [] as string[],
  quotes: [
    {
      symbol: "SPY",
      asset_class: "etf",
      price: "101.25",
      currency: "USD",
      change_percent: "0.42",
      observed_at: "2026-10-05T12:00:00+00:00",
      source: "twelvedata",
      last_known: false,
    },
    {
      symbol: "QQQ",
      asset_class: "etf",
      price: "202.50",
      currency: "USD",
      change_percent: "-0.18",
      observed_at: "2026-10-05T12:00:00+00:00",
      source: "twelvedata",
      last_known: false,
    },
  ],
};

const lastKnownOverview = {
  ...liveOverview,
  data_mode: "last_known",
  quotes: liveOverview.quotes.map((quote) => ({
    ...quote,
    observed_at: "2026-10-02T20:00:00+00:00",
    last_known: true,
  })),
};

const partialOverview = {
  ...liveOverview,
  quotes: liveOverview.quotes.slice(0, 1),
  unavailable: ["QQQ"],
};

const nothingOverview = {
  ...liveOverview,
  data_mode: "unavailable",
  quotes: [] as typeof liveOverview.quotes,
  unavailable: ["SPY", "QQQ"],
};

const asset = { symbol: "SPY", display_symbol: "SPY", asset_class: "etf", exchange: null, currency: "USD" };

const seriesBars = [
  {
    start_at: "2026-10-03T00:00:00+00:00",
    end_at: "2026-10-04T00:00:00+00:00",
    open: "99.00",
    high: "101.00",
    low: "98.50",
    close: "100.00",
    volume: "1000",
  },
  {
    start_at: "2026-10-04T00:00:00+00:00",
    end_at: "2026-10-05T00:00:00+00:00",
    open: "100.00",
    high: "102.00",
    low: "99.50",
    close: "101.25",
    volume: "1200",
  },
];

const series = {
  asset,
  interval: "1day",
  requested_days: 366,
  bars: seriesBars,
  overlays: {} as Record<string, (number | null)[]>,
  quality: {
    count: 2,
    first_at: seriesBars[0]?.start_at ?? null,
    last_at: seriesBars[1]?.start_at ?? null,
    duplicates_removed: 0,
    reordered: false,
    gap_count: 0,
    largest_gap_days: null,
    complete: true,
  },
  notes: [] as string[],
  provenance: {
    mode: "retrieved",
    available: true,
    source: "twelvedata",
    last_known: false,
    saved_at: null,
    delayed: null,
    market_open: null,
    observed_at: "2026-10-05T12:00:00+00:00",
    retrieved_at: "2026-10-05T12:00:00+00:00",
    age_seconds: 0,
    attempts: [],
    notes: [],
  },
};

const emptyWatchlist = { items: [] as unknown[], provenance: series.provenance };

const strategies = {
  active_strategy_id: "S-1",
  strategies: [{ strategy_id: "S-1", name: "Balanced", preferred_asset_classes: [] as string[] }],
  presets: [] as unknown[],
  note: "",
};

const unavailableStatus = {
  status: "unavailable",
  interpretation: null,
  agent: null,
  agent_version: null,
  correlation_id: null,
  request_id: null,
  reasoning_strategy: null,
  confidence: null,
  outcome: null,
  degraded: false,
  validation_status: null,
  warnings: ["SLAI runtime unavailable"],
};

const availableStatus = {
  ...unavailableStatus,
  status: "available",
  agent: "reasoning",
  agent_version: "2.3.0",
  warnings: [],
};

const analysisResponse = {
  symbol: "SPY",
  observation_count: 2,
  latest_close: 101.25,
  simple_return: 0.0125,
  rolling_volatility: null,
  maximum_drawdown: 0,
  technical: {
    sma: null,
    ema: null,
    momentum: null,
    rsi: null,
    macd: null,
    macd_signal: null,
    atr: null,
  },
  features: { simple_returns: [null, 0.0125] },
  reasoning: {
    status: "available",
    interpretation: "The supplied evidence shows a positive short-term move with limited history.",
    agent: "reasoning",
    agent_version: "2.3.0",
    correlation_id: "corr-1",
    request_id: "ui-1",
    reasoning_strategy: "cause_effect",
    confidence: 0.72,
    outcome: "supported",
    degraded: false,
    validation_status: "passed",
    warnings: [],
  },
};

function jsonResponse(data: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(data), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function installFetch(options: {
  overview?: typeof liveOverview | typeof lastKnownOverview | typeof partialOverview | typeof nothingOverview;
  slai?: typeof unavailableStatus | typeof availableStatus;
  marketError?: boolean;
  historyError?: boolean;
  watchlist?: typeof emptyWatchlist;
} = {}) {
  const overview = options.overview ?? liveOverview;
  const slai = options.slai ?? unavailableStatus;

  const mock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/api/v1/market/overview")) {
      return options.marketError
        ? jsonResponse({ detail: "market unavailable" }, 503)
        : jsonResponse(overview);
    }
    if (url.endsWith("/api/v1/integrations/slai")) {
      return jsonResponse(slai);
    }
    if (url.includes("/api/v1/market/series/")) {
      return options.historyError
        ? jsonResponse({ detail: "history unavailable" }, 503)
        : jsonResponse(series);
    }
    if (url.endsWith("/api/v1/market/watchlist")) {
      return jsonResponse(options.watchlist ?? emptyWatchlist);
    }
    if (url.endsWith("/api/v1/strategies")) {
      return jsonResponse(strategies);
    }
    if (url.endsWith("/api/v1/analysis/market")) {
      expect(init?.method).toBe("POST");
      expect(new Headers(init?.headers).get("X-Request-ID")).toMatch(/^slaifi-ui-/);
      const body = JSON.parse(String(init?.body));
      expect(body.asset.symbol).toBe("SPY");
      expect(body.bars).toHaveLength(2);
      return jsonResponse(analysisResponse);
    }
    throw new Error(`Unexpected request: ${url}`);
  });

  vi.stubGlobal("fetch", mock);
  return mock;
}

describe("MarketOverviewPage", () => {
  beforeEach(() => {
    document.documentElement.dataset.theme = "dark";
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders a loading state while API requests are pending", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => undefined)));
    render(<MarketOverviewPage />);
    expect(screen.getByText("Loading market snapshot")).toBeInTheDocument();
  });

  it("renders authoritative API quotes and never substitutes illustrative values", async () => {
    installFetch();
    render(<MarketOverviewPage />);

    expect(await screen.findByText("101.25")).toBeInTheDocument();
    expect(screen.getByText("202.50")).toBeInTheDocument();
    expect(screen.getByText("Live snapshot · USD")).toBeInTheDocument();
    expect(screen.queryByText("5,782.76")).not.toBeInTheDocument();
  });

  it("shows last known quotes clearly labelled with their observation time", async () => {
    installFetch({ overview: lastKnownOverview });
    render(<MarketOverviewPage />);

    expect(await screen.findByTestId("last-known-banner")).toHaveTextContent(/last known data/i);
    expect(screen.getByText("101.25")).toBeInTheDocument();
    expect(screen.getAllByTestId("last-known-note")).toHaveLength(2);
    expect(screen.getByTestId("snapshot-note")).toHaveTextContent("Last known data");
    expect(screen.getAllByTestId("watch-last-known").length).toBeGreaterThan(0);
  });

  it("says NOT AVAILABLE for a symbol with no live or saved price, and keeps the rest", async () => {
    installFetch({ overview: partialOverview });
    render(<MarketOverviewPage />);

    expect(await screen.findByText("101.25")).toBeInTheDocument();
    expect(screen.getByTestId("summary-unavailable")).toHaveTextContent("NOT AVAILABLE");
    expect(screen.getByTestId("watch-unavailable")).toHaveTextContent("QQQ");
    expect(screen.queryByText("202.50")).not.toBeInTheDocument();
  });

  it("says NOT AVAILABLE everywhere when nothing live or saved exists", async () => {
    installFetch({ overview: nothingOverview, historyError: true });
    render(<MarketOverviewPage />);

    expect(await screen.findByTestId("unavailable-banner")).toHaveTextContent("NOT AVAILABLE");
    expect(screen.getAllByTestId("summary-unavailable")).toHaveLength(2);
    expect(screen.getByTestId("snapshot-note")).toHaveTextContent("NOT AVAILABLE");
    expect(screen.queryByText(/\d{2,3}\.\d{2}/)).not.toBeInTheDocument();
  });

  it("requests SLAI reasoning only after real evidence exists and the user asks", async () => {
    const fetchMock = installFetch({ slai: availableStatus });
    const user = userEvent.setup();
    render(<MarketOverviewPage />);

    const button = await screen.findByRole("button", { name: /Explore the reasoning/i });
    await waitFor(() => expect(button).toBeEnabled());
    expect(fetchMock.mock.calls.filter((call) => String(call[0]).endsWith("/api/v1/analysis/market"))).toHaveLength(0);

    await user.click(button);

    expect(await screen.findByText("Evidence, in context.")).toBeInTheDocument();
    expect(screen.getByText(/positive short-term move/i)).toBeInTheDocument();
    expect(screen.getByText("cause_effect")).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter((call) => String(call[0]).endsWith("/api/v1/analysis/market"))).toHaveLength(1);
  });

  it("shows an unavailable state when market API fails without a fake fallback", async () => {
    installFetch({ marketError: true });
    render(<MarketOverviewPage />);

    expect((await screen.findAllByText(/NOT AVAILABLE/i)).length).toBeGreaterThan(0);
    expect(screen.queryByText("5,782.76")).not.toBeInTheDocument();
    expect(screen.queryByText(/illustrative fallback/i)).not.toBeInTheDocument();
  });

  it("exposes portfolio navigation and supports theme interaction", async () => {
    installFetch();
    const user = userEvent.setup();
    render(<MarketOverviewPage />);

    expect(screen.getByRole("link", { name: "My portfolio" })).toHaveAttribute("href", "#/portfolio");

    const theme = screen.getByRole("button", { name: "Toggle theme" });
    await user.click(theme);
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("light"));
  });

  it("charts the first indicator up to the chosen range and re-requests when the user asks for 5 years", async () => {
    const fetchMock = installFetch();
    const user = userEvent.setup();
    render(<MarketOverviewPage />);

    expect(await screen.findByRole("heading", { name: "SPY" })).toBeInTheDocument();
    const seriesCalls = () => fetchMock.mock.calls.map((call) => String(call[0])).filter((url) => url.includes("/market/series/SPY"));
    await waitFor(() => expect(seriesCalls().some((url) => url.includes("days=366"))).toBe(true));

    await user.click(screen.getByRole("button", { name: "5Y" }));

    await waitFor(() => expect(seriesCalls().some((url) => url.includes("days=1830"))).toBe(true));
    expect(screen.getByRole("button", { name: "5Y" })).toHaveAttribute("aria-pressed", "true");
  });

  it("remembers the chosen range in this browser and starts from it next time", async () => {
    installFetch();
    const user = userEvent.setup();
    const first = render(<MarketOverviewPage />);
    await user.click(await screen.findByRole("button", { name: "3M" }));
    first.unmount();

    installFetch();
    render(<MarketOverviewPage />);
    expect(await screen.findByRole("button", { name: "3M" })).toHaveAttribute("aria-pressed", "true");
  });

  it("says NOT AVAILABLE on the chart when there is no history, instead of drawing anything", async () => {
    installFetch({ historyError: true });
    render(<MarketOverviewPage />);

    await waitFor(() => expect(screen.queryByTestId("market-chart-svg")).not.toBeInTheDocument());
    expect((await screen.findAllByText(/NOT AVAILABLE/i)).length).toBeGreaterThan(0);
  });

  it("shows the user's own assets in Market watch, with NOT AVAILABLE for one that has no quote", async () => {
    installFetch({
      watchlist: {
        items: [{ asset: { symbol: "KO", display_symbol: "NYSE:KO", asset_class: "stock", exchange: "NYSE", currency: "USD" }, name: "Coca-Cola", added_at: "2026-10-05T12:00:00+00:00", quote: null }],
        provenance: series.provenance,
      },
    });
    render(<MarketOverviewPage />);

    expect(await screen.findByText("NYSE:KO")).toBeInTheDocument();
    expect(screen.getByTestId("watch-unavailable")).toHaveTextContent("NOT AVAILABLE");
    expect(screen.queryByTestId("watch-default-note")).not.toBeInTheDocument();
  });

  it("says plainly that the list is the default indicators until the user adds assets", async () => {
    installFetch();
    render(<MarketOverviewPage />);

    expect(await screen.findByTestId("watch-default-note")).toHaveTextContent(/default market indicators/i);
  });
});
