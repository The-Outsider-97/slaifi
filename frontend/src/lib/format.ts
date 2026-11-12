/** Number, date and label formatting shared by the finance screens. */

export function money(value: string | number | null | undefined, currency = "USD"): string {
  if (value === null || value === undefined || value === "") return "—";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(numeric);
  } catch {
    return numeric.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
}

/** A fraction (0.05) rendered as a percentage ("5.00%"). null/NaN render as an em dash, never as 0. */
export function percent(rate: number | null | undefined, digits = 2): string {
  if (rate === null || rate === undefined || !Number.isFinite(rate)) return "—";
  return `${(rate * 100).toFixed(digits)}%`;
}

export function signedPercent(rate: number | null | undefined, digits = 2): string {
  if (rate === null || rate === undefined || !Number.isFinite(rate)) return "—";
  const text = `${(rate * 100).toFixed(digits)}%`;
  return rate > 0 ? `+${text}` : text;
}

export function quantity(value: string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";
  return numeric.toLocaleString("en-US", { maximumFractionDigits: 8 });
}

export function number(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return value.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function direction(value: number | string | null | undefined): "positive" | "negative" | "neutral" {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric === 0) return "neutral";
  return numeric > 0 ? "positive" : "negative";
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(date);
}

export function shortDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "2-digit" }).format(date);
}

export function age(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "age unknown";
  if (seconds < 90) return `${Math.round(seconds)}s old`;
  if (seconds < 5400) return `${Math.round(seconds / 60)} min old`;
  if (seconds < 172_800) return `${Math.round(seconds / 3600)} h old`;
  return `${Math.round(seconds / 86_400)} days old`;
}

export function humanize(code: string): string {
  const text = code.replace(/[_-]+/g, " ").trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : text;
}

/** "trend_vs_sma50" → "Trend vs SMA 50"; indicator acronyms stay upper-case. */
export function signalLabel(name: string): string {
  const text = humanize(name)
    .replace(/\b(rsi|macd|sma|ema|atr|adx)(?:\s?(\d+))?\b/gi, (_, word: string, digits?: string) =>
      `${word.toUpperCase()}${digits ? ` ${digits}` : ""}`,
    )
    .replace(/\bvs\b/gi, "vs");
  return text;
}
