import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MarketOverviewPage } from "./MarketOverviewPage";

const liveOverview = {
  generated_at: "2026-10-05T12:00:00+00:00",
  data_mode: "live",
  quotes: [
    {
      symbol: "SPY",
      asset_class: "etf",
      price: "101.25",
      currency: "USD",
      change_percent: "0.42",
      observed_at: "2026-10-05T12:00:00+00:00",
      source: "twelvedata",
    },
    {
      symbol: "QQQ",
      asset_class: "etf",
      price: "202.50",
      currency: "USD",
      change_percent: "-0.18",
      observed_at: "2026-10-05T12:00:00+00:00",
      source: "twelvedata",
    },
  ],
};

const mockOverview = {
  ...liveOverview,
  data_mode: "mock",
  quotes: liveOverview.quotes.map((quote) => ({ ...quote, source: "mock" })),
};

const history = {
  symbol: "SPY",
  asset_class: "etf",
  interval: "1day",
  generated_at: "2026-10-05T12:00:00+00:00",
  data_mode: "live",
  bars: [
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
  ],
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
  overview?: typeof liveOverview | typeof mockOverview;
  slai?: typeof unavailableStatus | typeof availableStatus;
  marketError?: boolean;
  historyError?: boolean;
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
    if (url.includes("/api/v1/market/history/SPY")) {
      return options.historyError
        ? jsonResponse({ detail: "history unavailable" }, 503)
        : jsonResponse(history);
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
    expect(screen.getByText("Market snapshot · USD")).toBeInTheDocument();
    expect(screen.queryByText("5,782.76")).not.toBeInTheDocument();
  });

  it("hides mock financial values instead of presenting them as real", async () => {
    installFetch({ overview: mockOverview });
    render(<MarketOverviewPage />);

    expect(await screen.findByText(/Mock provider is configured/i)).toBeInTheDocument();
    expect(screen.queryByText("101.25")).not.toBeInTheDocument();
    expect(screen.queryByText("202.50")).not.toBeInTheDocument();
  });

  it("requests SLAI reasoning only after real evidence exists and the user asks", async () => {
    const fetchMock = installFetch({ slai: availableStatus });
    const user = userEvent.setup();
    render(<MarketOverviewPage />);

    const button = await screen.findByRole("button", { name: /Explore the reasoning/i });
    await waitFor(() => expect(button).toBeEnabled());
    expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/api/v1/analysis/market"))).toHaveLength(0);

    await user.click(button);

    expect(await screen.findByText("Evidence, in context.")).toBeInTheDocument();
    expect(screen.getByText(/positive short-term move/i)).toBeInTheDocument();
    expect(screen.getByText("cause_effect")).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/api/v1/analysis/market"))).toHaveLength(1);
  });

  it("shows an unavailable state when market API fails without a fake fallback", async () => {
    installFetch({ marketError: true });
    render(<MarketOverviewPage />);

    expect(await screen.findByText(/Market data unavailable/i)).toBeInTheDocument();
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
});
