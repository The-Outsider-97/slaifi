import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MyPortfolioPage } from "./MyPortfolioPage";

const deterministicPortfolio = {
  snapshot: {
    portfolio_id: "primary",
    as_of: "2026-10-05T12:00:00+00:00",
    base_currency: "USD",
    cash_balance: "800",
    securities_market_value: "240",
    total_value: "1040",
    positions: [
      {
        asset: "ABC",
        quantity: "2",
        average_cost: "100",
        realized_pnl: "0",
        market_price: "120",
        market_value: "240",
        unrealized_pnl: "40",
        portfolio_weight: 240 / 1040,
      },
    ],
  },
  risk: null,
  goals: null,
  reasoning: null,
};

const reasonedPortfolio = {
  ...deterministicPortfolio,
  reasoning: {
    status: "available",
    interpretation: "The portfolio is concentrated in a single supplied position.",
    agent: "reasoning",
    agent_version: "2.3.0",
    correlation_id: "portfolio-correlation",
    request_id: "portfolio-ui",
    reasoning_strategy: "cause_effect",
    confidence: 0.7,
    outcome: "supported",
    degraded: false,
    validation_status: "passed",
    warnings: [],
  },
};

function jsonResponse(data: unknown, status = 200) {
  return Promise.resolve(
    new Response(status === 204 ? null : JSON.stringify(data), {
      status,
      headers: status === 204 ? undefined : { "Content-Type": "application/json" },
    }),
  );
}

describe("MyPortfolioPage", () => {
  beforeEach(() => {
    document.documentElement.dataset.theme = "dark";
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("loads deterministic portfolio state without requesting SLAI reasoning", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      expect(String(input)).toContain("include_reasoning=false");
      return jsonResponse(deterministicPortfolio);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<MyPortfolioPage />);

    expect(await screen.findByText("$1,040.00")).toBeInTheDocument();
    expect(screen.getByText("ABC")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Explore the reasoning/i })).toBeEnabled();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("requests SLAI reasoning only after the user asks for it", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("include_reasoning=true")) {
        expect(new Headers(init?.headers).get("X-Request-ID")).toMatch(/^slaifi-ui-/);
        return jsonResponse(reasonedPortfolio);
      }
      if (url.includes("include_reasoning=false")) {
        return jsonResponse(deterministicPortfolio);
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<MyPortfolioPage />);

    const button = await screen.findByRole("button", { name: /Explore the reasoning/i });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await user.click(button);

    expect(await screen.findByText("What stands out.")).toBeInTheDocument();
    expect(screen.getByText(/concentrated in a single supplied position/i)).toBeInTheDocument();
    expect(screen.getByText("passed")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("renders a truthful empty state for an unconfigured portfolio", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse(null, 204)));
    render(<MyPortfolioPage />);

    expect(await screen.findByText("Your portfolio is empty.")).toBeInTheDocument();
    expect(screen.getByText(/No holdings, values or returns have been invented/i)).toBeInTheDocument();
  });

  it("keeps deterministic portfolio visible when an insight request fails", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("include_reasoning=true")) {
        return jsonResponse({ detail: "SLAI unavailable" }, 503);
      }
      return jsonResponse(deterministicPortfolio);
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<MyPortfolioPage />);
    await screen.findByText("$1,040.00");
    await user.click(screen.getByRole("button", { name: /Explore the reasoning/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("SLAI unavailable");
    expect(screen.getByText("$1,040.00")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: /Explore the reasoning/i })).toBeEnabled());
  });
});
