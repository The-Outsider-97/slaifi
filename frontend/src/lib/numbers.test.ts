import { describe, expect, it } from "vitest";

import { parseNumber, parseOptional, percentToFraction, type NumberRules } from "./numbers";

const money: NumberRules = { label: "Starting capital", min: 0, maxDecimals: 2 };

describe("parseNumber", () => {
  it("accepts how people really write amounts", () => {
    for (const [typed, text] of [
      ["5000", "5000"],
      ["$5,000", "5000"],
      ["5000 USD", "5000"],
      ["usd 5,000.50", "5000.50"],
      ["  1 000 ", "1000"],
    ] as const) {
      const out = parseNumber(typed, money);
      expect(out.ok && out.text).toBe(text);
    }
  });

  it("explains a currency word typed instead of an amount", () => {
    const out = parseNumber("USD", money);
    expect(out.ok).toBe(false);
    if (!out.ok) {
      expect(out.message).toContain("Starting capital");
      expect(out.message).toContain("currency, not an amount");
    }
  });

  it("explains other bad input in plain words", () => {
    const text = (s: string, rules = money) => {
      const out = parseNumber(s, rules);
      return out.ok ? "" : out.message;
    };
    expect(text("abc")).toContain("is not a number");
    expect(text("1.2.3")).toContain("is not a number");
    expect(text("12,5")).toContain("use a dot");
    expect(text("-5")).toContain("cannot be negative");
    expect(text("0", { label: "Target", min: 0, minExclusive: true })).toContain("more than zero");
    expect(text("1.234")).toContain("at most 2 decimal places");
    expect(text("", money)).toContain("enter a number");
    expect(text("150", { label: "Years", max: 100 })).toContain("cannot be more than 100");
  });

  it("accepts a percent sign where the box is a percentage", () => {
    const out = parseNumber("6%", { label: "Return", percent: true });
    expect(out.ok && out.value).toBe(6);
    expect(parseNumber("6%", { label: "Return" }).ok).toBe(false);
  });

  it("treats an empty optional box as absent", () => {
    expect(parseOptional("  ", money)).toBe(null);
    expect(parseOptional("5", money)?.ok).toBe(true);
  });

  it("converts percentages to fractions without float noise", () => {
    expect(percentToFraction(6)).toBe(0.06);
    expect(percentToFraction(0.1)).toBe(0.001);
  });
});
