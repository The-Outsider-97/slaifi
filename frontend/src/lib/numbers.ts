/**
 * Reading numbers people type into forms.
 *
 * People write "5,000", "$5000", "5000 USD" and "6%". These are accepted and cleaned. Things that
 * are not numbers ("USD", "abc", "1.2.3") get a sentence that names the box and says what to type,
 * before anything is sent to the server.
 */

export type Parsed = { ok: true; value: number; text: string } | { ok: false; message: string };

export type NumberRules = {
  /** The label of the box, used to start the message. */
  label: string;
  min?: number;
  /** When true the minimum itself is not allowed (e.g. an amount must be above 0). */
  minExclusive?: boolean;
  max?: number;
  maxDecimals?: number;
  /** A trailing % is accepted and removed (the box already says percent). */
  percent?: boolean;
};

const CURRENCY_WORDS = /\b(usd|eur|gbp|cad|aud|chf|jpy|dollars?|euros?|pounds?|bucks)\b/gi;
const SYMBOLS = /[$€£¥]/g;
const THOUSANDS = /^[+-]?\d{1,3}(,\d{3})+(\.\d+)?$/;
const PLAIN = /^[+-]?(\d+(\.\d*)?|\.\d+)$/;

function tidy(value: number): string {
  return String(Number(value.toFixed(10)));
}

export function parseNumber(raw: string, rules: NumberRules): Parsed {
  const { label } = rules;
  const shown = raw.trim();
  if (shown === "") return { ok: false, message: `${label}: enter a number.` };

  let text = shown.replace(CURRENCY_WORDS, "").replace(SYMBOLS, "").replace(/\s+/g, "");
  if (rules.percent) text = text.replace(/%$/, "");

  if (text === "") {
    const isCurrency = /^[a-z]{3}$/i.test(shown) || /dollar|euro|pound/i.test(shown);
    return {
      ok: false,
      message: isCurrency
        ? `${label}: “${shown}” is a currency, not an amount. Type digits such as 5000 (the currency is chosen elsewhere).`
        : `${label}: enter a number.`,
    };
  }
  if (THOUSANDS.test(text)) text = text.replace(/,/g, "");
  if (!PLAIN.test(text)) {
    const decimalComma = /^\d+,\d{1,2}$/.test(text);
    return {
      ok: false,
      message: decimalComma
        ? `${label}: use a dot for decimals (5000.50), not a comma.`
        : `${label}: “${shown}” is not a number. Use digits only, for example 5000 or 5000.50.`,
    };
  }

  const value = Number(text);
  if (!Number.isFinite(value)) return { ok: false, message: `${label}: that number is too large.` };
  if (rules.maxDecimals !== undefined) {
    const places = (text.split(".")[1] ?? "").length;
    if (places > rules.maxDecimals) {
      return {
        ok: false,
        message:
          rules.maxDecimals === 0
            ? `${label}: use a whole number.`
            : `${label}: at most ${rules.maxDecimals} decimal places.`,
      };
    }
  }
  if (rules.min !== undefined) {
    const bad = rules.minExclusive ? value <= rules.min : value < rules.min;
    if (bad) {
      const message =
        rules.min === 0
          ? rules.minExclusive
            ? `${label}: must be more than zero.`
            : `${label}: cannot be negative.`
          : rules.minExclusive
            ? `${label}: must be more than ${rules.min}.`
            : `${label}: cannot be less than ${rules.min}.`;
      return { ok: false, message };
    }
  }
  if (rules.max !== undefined && value > rules.max) {
    return { ok: false, message: `${label}: cannot be more than ${rules.max}.` };
  }
  const clean = text.replace(/^\+/, "").replace(/\.$/, "");
  return { ok: true, value, text: clean === "" || clean === "-" ? tidy(value) : clean };
}

/** A box that may be left empty: empty → ``null``, anything else must parse. */
export function parseOptional(raw: string, rules: NumberRules): Parsed | null {
  return raw.trim() === "" ? null : parseNumber(raw, rules);
}

/** A percentage typed as 6 or 6% becomes the fraction 0.06. */
export function percentToFraction(value: number): number {
  return Number((value / 100).toFixed(10));
}
