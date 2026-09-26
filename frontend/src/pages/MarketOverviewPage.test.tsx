import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MarketOverviewPage } from "./MarketOverviewPage";

const marketOverview = {
  generated_at: "2026-09-25T18:00:00+00:00",
  data_mode: "mock",
  quotes: [
    { symbol: "SPY", asset_class: "etf", price: "100.00", currency: "USD", change_percent: "0.42", observed_at: "2026-09-25T18:00:00+00:00", source: "mock" },
    { symbol: "QQQ", asset_class: "etf", price: "200.00", currency: "USD", change_percent: "-0.18", observed_at: "2026-09-25T18:00:00+00:00", source: "mock" },
    { symbol: "DIA", asset_class: "etf", price: "150.00", currency: "USD", change_percent: "0.11", observed_at: "2026-09-25T18:00:00+00:00", source: "mock" },
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
  symbol: "SPX",
  observation_count: 44,
  latest_close: 5782.76,
  simple_return: 0.006,
  rolling_volatility: 0.13,
  maximum_drawdown: -0.04,
  technical: { sma: 5750, ema: 5754, momentum: 0.02, rsi: 58, macd: 12, macd_signal: 10, atr: 35 },
  features: { simple_returns: [null, 0.01] },
  reasoning: {
    status: "available",
    interpretation: "Momentum is positive, while recent drawdowns still argue for selectivity.",
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
  return Promise.resolve(new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  }));
}

function installFetch(slaiStatus: typeof unavailableStatus | typeof availableStatus, options: { marketError?: boolean } = {}) {
  const mock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/api/v1/market/overview")) {
      return options.marketError ? jsonResponse({ detail: "market unavailable" }, 503) : jsonResponse(marketOverview);
    }
    if (url.endsWith("/api/v1/integrations/slai")) return jsonResponse(slaiStatus);
    if (url.endsWith("/api/v1/analysis/market")) {
      expect(init?.method).toBe("POST");
      expect(new Headers(init?.headers).get("X-Request-ID")).toMatch(/^slaifi-ui-/);
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

  it("keeps mock market values illustrative and labels SLAI as unavailable", async () => {
    installFetch(unavailableStatus);
    render(<MarketOverviewPage />);

    expect(await screen.findByText("5,782.76")).toBeInTheDocument();
    expect(screen.queryByText("100.00")).not.toBeInTheDocument();
    expect(screen.getByText("Illustrative market snapshot · USD")).toBeInTheDocument();
    expect(screen.getByText("Illustrative analysis · SLAI engine unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Explore the reasoning/i })).toBeDisabled();
    expect(screen.getByText(/Illustrative sample signals/i)).toBeInTheDocument();
  });

  it("requests real SLAI interpretation and renders public provenance when available", async () => {
    const fetchMock = installFetch(availableStatus);
    const user = userEvent.setup();
    render(<MarketOverviewPage />);

    const button = await screen.findByRole("button", { name: /Explore the reasoning/i });
    expect(button).toBeEnabled();
    await user.click(button);

    expect(await screen.findByText("Evidence, in context.")).toBeInTheDocument();
    expect(screen.getByText(/Momentum is positive/)).toBeInTheDocument();
    expect(screen.getByText("cause_effect")).toBeInTheDocument();
    expect(screen.getByText("SLAI analysis · illustrative data · reasoning v2.3.0 · available")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("uses explicitly labelled fallback values when the market API fails", async () => {
    installFetch(unavailableStatus, { marketError: true });
    render(<MarketOverviewPage />);

    expect(await screen.findByText(/Market API unavailable/i)).toBeInTheDocument();
    expect(screen.getByText("5,782.76")).toBeInTheDocument();
    expect(screen.getByText(/illustrative fallback/i)).toBeInTheDocument();
  });

  it("exposes workspace navigation and supports mobile-menu interaction", async () => {
    installFetch(unavailableStatus);
    const user = userEvent.setup();
    render(<MarketOverviewPage />);

    expect(screen.getByRole("link", { name: "My portfolio" })).toHaveAttribute("href", "#portfolio");
    const menu = screen.getByRole("button", { name: "Toggle navigation" });
    await user.click(menu);
    expect(screen.getByLabelText("Workspace navigation")).toHaveClass("sidebar--open");

    const theme = screen.getByRole("button", { name: "Toggle theme" });
    await user.click(theme);
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("light"));
  });
});
