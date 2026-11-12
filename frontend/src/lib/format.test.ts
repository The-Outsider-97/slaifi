import { describe, expect, it } from "vitest";

import { age, direction, money, percent, quantity, signalLabel, signedPercent } from "./format";

describe("format", () => {
  it("never renders a missing number as zero", () => {
    expect(percent(null)).toBe("—");
    expect(percent(Number.NaN)).toBe("—");
    expect(money(null)).toBe("—");
    expect(money("abc")).toBe("—");
    expect(signedPercent(undefined)).toBe("—");
  });

  it("formats fractions as percentages", () => {
    expect(percent(0.0523)).toBe("5.23%");
    expect(signedPercent(0.05)).toBe("+5.00%");
    expect(signedPercent(-0.05)).toBe("-5.00%");
    expect(percent(0.1, 0)).toBe("10%");
  });

  it("formats money with the portfolio currency", () => {
    expect(money("1234.5")).toBe("$1,234.50");
    expect(money(10, "EUR")).toContain("10.00");
  });

  it("keeps quantity precision without trailing noise", () => {
    expect(quantity("5.00000000")).toBe("5");
    expect(quantity("0.12345678")).toBe("0.12345678");
  });

  it("maps the sign of a value to a direction", () => {
    expect(direction("-0.01")).toBe("negative");
    expect(direction(0)).toBe("neutral");
    expect(direction(null)).toBe("neutral");
    expect(direction(3)).toBe("positive");
  });

  it("describes data age in plain words", () => {
    expect(age(null)).toBe("age unknown");
    expect(age(30)).toBe("30s old");
    expect(age(600)).toBe("10 min old");
    expect(age(7200)).toBe("2 h old");
  });

  it("keeps indicator acronyms upper-case", () => {
    expect(signalLabel("rsi14")).toContain("RSI");
    expect(signalLabel("macd_histogram")).toBe("MACD histogram");
    expect(signalLabel("trend_vs_sma50")).toBe("Trend vs SMA 50");
  });
});
