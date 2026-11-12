import { describe, expect, it } from "vitest";

import { routeFromHash } from "./App";

describe("routeFromHash", () => {
  it("defaults to the market overview", () => {
    expect(routeFromHash("")).toEqual({ page: "market", param: null });
    expect(routeFromHash("#/unknown")).toEqual({ page: "market", param: null });
  });

  it("routes every section", () => {
    for (const page of ["market", "analysis", "portfolio", "paper", "advisor", "strategy", "settings"]) {
      expect(routeFromHash(`#/${page}`).page).toBe(page);
    }
  });

  it("passes a path parameter such as a symbol", () => {
    expect(routeFromHash("#/analysis/BTC%2FUSD")).toEqual({ page: "analysis", param: "BTC/USD" });
  });

  it("keeps the legacy portfolio sub-path working", () => {
    expect(routeFromHash("#/portfolio/anything").page).toBe("portfolio");
  });
});
