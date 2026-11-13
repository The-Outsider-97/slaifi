import { useRef, useState, type FormEvent } from "react";

import { useAction } from "../../hooks/useAsync";
import { dateTime, humanize, money, quantity } from "../../lib/format";
import { parseNumber } from "../../lib/numbers";
import { placeOrder, previewOrder, type OrderBody } from "../../services/finance";
import type { OrderOutcome, PortfolioView } from "../../types/finance";
import { FreshnessBadge } from "./FreshnessBadge";
import { Notice, Simulated } from "./Notice";

function newOrderId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return `ui-${crypto.randomUUID()}`;
  return `ui-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function OutcomeDetails({ outcome, currency }: { outcome: OrderOutcome; currency: string }) {
  const { decision } = outcome;
  const ex = decision.execution;
  return (
    <div className="stack" data-testid="order-outcome">
      <div className="order-outcome__head">
        <strong>
          {decision.status === "filled"
            ? outcome.dry_run
              ? "Preview: this order would be filled"
              : outcome.duplicate
                ? "Already executed (no new order was placed)"
                : "Simulated order filled"
            : "Order rejected"}
        </strong>
        <Simulated />
      </div>
      {decision.rejections.length ? (
        <ul className="plain-list negative-text">
          {decision.rejections.map((r) => (
            <li key={r.code + r.message}>
              {r.message} <small>({humanize(r.code)})</small>
            </li>
          ))}
        </ul>
      ) : null}
      {ex ? (
        <dl className="facts facts--stack">
          <div><dt>Quote used</dt><dd>{money(ex.quote_price, ex.currency)}</dd><small>{ex.quote_source} · observed {dateTime(ex.quote_observed_at)}</small></div>
          <div><dt>Simulated fill price</dt><dd>{money(ex.execution_price, ex.currency)}</dd><small>includes {money(ex.slippage_per_unit, ex.currency)} per unit slippage</small></div>
          <div><dt>Fees</dt><dd>{money(ex.commission, ex.currency)}</dd></div>
          <div><dt>Gross amount</dt><dd>{money(ex.gross_amount, ex.currency)}</dd></div>
          <div><dt>Cash effect</dt><dd>{money(ex.net_cash_effect, ex.currency)}</dd></div>
          <div><dt>Quantity</dt><dd>{decision.trade ? quantity(decision.trade.quantity) : "see preview"}</dd></div>
        </dl>
      ) : null}
      {ex?.market_open === false ? <Notice tone="warning">The market was closed when this quote was observed.</Notice> : null}
      {decision.warnings.map((w) => (
        <Notice key={w} tone="info">{w}</Notice>
      ))}
      {ex?.notes.map((n) => (
        <small className="muted" key={n}>{n}</small>
      ))}
      {outcome.portfolio ? <small className="muted">New cash balance {money(outcome.portfolio.cash_balance, currency)}.</small> : null}
    </div>
  );
}

type Side = "buy" | "sell" | "short" | "cover";

const SIDES: { value: Side; label: string; hint: string }[] = [
  { value: "buy", label: "Buy", hint: "Buy shares to hold. You gain if the price rises." },
  { value: "sell", label: "Sell", hint: "Sell shares you hold." },
  {
    value: "short",
    label: "Short",
    hint: "Sell borrowed shares, hoping to buy them back cheaper. You gain if the price falls and lose if it rises: a short can lose more than the amount you receive. The proceeds and a further 50 % stay locked as collateral. Needs a strategy with a short limit above 0.",
  },
  { value: "cover", label: "Cover", hint: "Buy back shares you are short to close or reduce the short." },
];

type Props = {
  portfolio: PortfolioView;
  initialSymbol?: string;
  onFilled: () => void;
};

/** Two steps on purpose: preview the exact simulated fill, then explicitly confirm it. */
export function OrderTicket({ portfolio, initialSymbol = "", onFilled }: Props) {
  const [symbol, setSymbol] = useState(initialSymbol);
  const [side, setSide] = useState<Side>("buy");
  const [mode, setMode] = useState<"quantity" | "notional">("quantity");
  const [amount, setAmount] = useState("");
  const [previewed, setPreviewed] = useState<OrderBody | null>(null);
  const orderId = useRef(newOrderId());

  const preview = useAction(previewOrder);
  const place = useAction(placeOrder);

  const parsedAmount = parseNumber(amount, {
    label: mode === "quantity" ? "Quantity" : "Amount",
    min: 0,
    minExclusive: true,
    maxDecimals: mode === "quantity" ? 8 : 2,
  });
  const amountProblem = amount.trim() !== "" && !parsedAmount.ok ? parsedAmount.message : "";

  const body = (): OrderBody | null => {
    const sym = symbol.trim().toUpperCase();
    const parsed = parsedAmount;
    if (!sym || !parsed.ok) return null;
    return { symbol: sym, side, [mode]: parsed.text, client_order_id: orderId.current };
  };

  const submitPreview = async (event: FormEvent) => {
    event.preventDefault();
    const next = body();
    if (!next) return;
    place.clear();
    const outcome = await preview.run(portfolio.portfolio.portfolio_id, next);
    setPreviewed(outcome?.decision.status === "filled" ? next : null);
  };

  const confirm = async () => {
    if (!previewed) return;
    const outcome = await place.run(portfolio.portfolio.portfolio_id, previewed);
    if (outcome) {
      setPreviewed(null);
      preview.clear();
      if (outcome.decision.status === "filled") {
        orderId.current = newOrderId();
        setAmount("");
        onFilled();
      }
    }
  };

  const edit = () => {
    setPreviewed(null);
    preview.clear();
  };

  const shown = place.result ?? preview.result;

  return (
    <section className="panel analysis-panel" aria-labelledby="ticket-title">
      <div className="panel-heading">
        <div>
          <span className="section-kicker">SIMULATED ORDER</span>
          <h2 id="ticket-title">Order ticket</h2>
        </div>
        <Simulated />
      </div>

      <form className="stack" onSubmit={submitPreview} aria-label="Paper order">
        <div className="form-grid">
          <label className="field">
            <span>Symbol</span>
            <input value={symbol} onChange={(e) => { setSymbol(e.target.value); edit(); }} maxLength={24} placeholder="e.g. JNJ" required />
          </label>
          <fieldset className="segmented" aria-label="Side">
            {SIDES.map((item) => (
              <label key={item.value} className={side === item.value ? "segmented__item segmented__item--active" : "segmented__item"}>
                <input type="radio" name="side" value={item.value} checked={side === item.value} onChange={() => { setSide(item.value); edit(); }} />
                {item.label}
              </label>
            ))}
          </fieldset>
          <fieldset className="segmented" aria-label="Order size by">
            {(["quantity", "notional"] as const).map((item) => (
              <label key={item} className={mode === item ? "segmented__item segmented__item--active" : "segmented__item"}>
                <input type="radio" name="mode" value={item} checked={mode === item} onChange={() => { setMode(item); edit(); }} />
                {item === "quantity" ? "By quantity" : `By amount (${portfolio.currency})`}
              </label>
            ))}
          </fieldset>
          <p className="order-risk-note" role="note" data-testid="side-hint">
            {SIDES.find((item) => item.value === side)?.hint}
          </p>
          <label className="field">
            <span>{mode === "quantity" ? "Quantity" : `Amount (${portfolio.currency})`}</span>
            <input
              inputMode="decimal"
              value={amount}
              onChange={(e) => { setAmount(e.target.value); edit(); }}
              placeholder={mode === "quantity" ? "number of shares" : "amount in dollars"}
              aria-invalid={Boolean(amountProblem)}
              required
            />
            {amountProblem ? <small className="field-error" role="alert">{amountProblem}</small> : null}
          </label>
        </div>
        <button className="primary-cta" type="submit" disabled={preview.running || !body()}>
          <span>{preview.running ? "Pricing…" : "Preview simulated order"}</span>
          <span aria-hidden="true">→</span>
        </button>
      </form>

      {preview.error ? <Notice tone="error">{preview.error}</Notice> : null}
      {place.error ? <Notice tone="error">{place.error}</Notice> : null}

      {shown ? (
        <div className="stack ticket-result">
          <FreshnessBadge provenance={shown.decision.execution ? {
            mode: shown.decision.execution.data_mode,
            available: true,
            source: shown.decision.execution.quote_source,
            last_known: false,
            saved_at: null,
            delayed: shown.decision.execution.data_mode === "delayed" ? true : null,
            market_open: shown.decision.execution.market_open,
            observed_at: shown.decision.execution.quote_observed_at,
            retrieved_at: null,
            age_seconds: null,
            attempts: [],
            notes: [],
          } : null} />
          <OutcomeDetails outcome={shown} currency={portfolio.currency} />
        </div>
      ) : null}

      {previewed ? (
        <div className="confirm-bar" role="group" aria-label="Confirm simulated order">
          <span>
            Place this <strong>simulated</strong> {previewed.side === "short" ? "short sale" : previewed.side === "cover" ? "cover (buy-back)" : previewed.side} of {previewed.symbol}? No real money is involved.
          </span>
          <div>
            <button type="button" className="secondary-button" onClick={edit}>Edit</button>
            <button type="button" className="primary-cta primary-cta--inline" disabled={place.running} onClick={() => void confirm()}>
              {place.running ? "Placing…" : "Confirm simulated order"}
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
