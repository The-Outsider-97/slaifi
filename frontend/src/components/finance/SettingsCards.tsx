import { useState, type FormEvent } from "react";
import { useAction, useAsync } from "../../hooks/useAsync";
import { parseNumber } from "../../lib/numbers";
import { checkProviders, fetchPlatformFees, removeProviderKey, saveProviderKey, savePlatformFees } from "../../services/finance";
import type { ProviderCheck, ProviderKeyInfo } from "../../types/finance";
import { Loading, Notice } from "./Notice";

function sourceText(source: ProviderKeyInfo["source"]): string {
  if (source === "settings") return "Saved in SLAIFI (used instead of .env)";
  if (source === "environment") return "From the .env file or environment";
  return "No key yet";
}

/**
 * Add, replace or remove one market-data key. The key is typed into a password box, sent once and
 * never shown again: the page only learns where the key comes from, never what it is.
 */
export function ProviderKeyEditor({ info, onChanged }: { info: ProviderKeyInfo; onChanged: () => void }) {
  const [value, setValue] = useState("");
  const [verdict, setVerdict] = useState<ProviderCheck | null>(null);
  const save = useAction(saveProviderKey);
  const remove = useAction(removeProviderKey);
  const test = useAction(checkProviders);
  const busy = save.running || remove.running || test.running;

  const runCheck = async () => {
    const done = await test.run(info.name);
    setVerdict(done?.checks.find((c) => c.name === info.name) ?? null);
  };

  const onSave = async (event: FormEvent) => {
    event.preventDefault();
    if (value.trim() === "") return;
    if (await save.run(info.name, value)) {
      setValue("");
      setVerdict(null);
      onChanged();
      await runCheck();
      onChanged();
    }
  };

  const onRemove = async () => {
    if (await remove.run(info.name)) {
      setVerdict(null);
      onChanged();
    }
  };

  return (
    <form className="key-editor" onSubmit={(e) => void onSave(e)} data-testid={`key-${info.name}`}>
      <span className={info.configured ? "positive-text" : undefined} data-testid={`key-source-${info.name}`}>
        {sourceText(info.source)}
      </span>
      <div className="inline-form">
        <label className="field field--grow">
          <span className="visually-hidden">{info.label} API key</span>
          <input
            type="password"
            autoComplete="off"
            spellCheck={false}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={info.configured ? "Paste a new key to replace it" : "Paste your API key"}
            aria-label={`${info.label} API key`}
          />
        </label>
        <button type="submit" className="secondary-button" disabled={busy || value.trim() === ""}>
          {save.running ? "Saving…" : "Save key"}
        </button>
        {info.configured ? (
          <button type="button" className="secondary-button" disabled={busy} onClick={() => void runCheck()}>
            {test.running ? "Testing…" : "Test"}
          </button>
        ) : null}
        {info.source === "settings" ? (
          <button type="button" className="secondary-button" disabled={busy} onClick={() => void onRemove()}>
            Remove
          </button>
        ) : null}
      </div>
      {verdict ? (
        <small className="block" data-testid={`key-check-${info.name}`}>
          {verdict.ok ? "✓" : "✗"} {verdict.detail}
        </small>
      ) : null}
      {save.error ? <Notice tone="error">{save.error}</Notice> : null}
      {remove.error ? <Notice tone="error">{remove.error}</Notice> : null}
      {test.error ? <Notice tone="error">{test.error}</Notice> : null}
    </form>
  );
}

/** The flat fees the trading platform charges. Starts at 1.00 each; change them to match your platform. */
export function PlatformFeesCard() {
  const fees = useAsync((signal) => fetchPlatformFees(signal), "platform-fees");
  const save = useAction(savePlatformFees);
  const [trade, setTrade] = useState<string | null>(null);
  const [withdrawal, setWithdrawal] = useState<string | null>(null);
  const [problem, setProblem] = useState("");

  const shownTrade = trade ?? fees.data?.per_trade ?? "";
  const shownWithdrawal = withdrawal ?? fees.data?.per_withdrawal ?? "";
  const dirty = trade !== null || withdrawal !== null;

  const onSave = async (event: FormEvent) => {
    event.preventDefault();
    const rules = { min: 0, max: 1000, maxDecimals: 2 } as const;
    const t = parseNumber(shownTrade, { label: "Fee per transaction", ...rules });
    if (!t.ok) return setProblem(t.message);
    const w = parseNumber(shownWithdrawal, { label: "Fee per withdrawal", ...rules });
    if (!w.ok) return setProblem(w.message);
    setProblem("");
    if (await save.run({ per_trade: t.text, per_withdrawal: w.text })) {
      setTrade(null);
      setWithdrawal(null);
      fees.reload();
    }
  };

  return (
    <section className="panel analysis-panel" aria-labelledby="fees-title" data-testid="platform-fees">
      <div className="panel-heading">
        <div>
          <span className="section-kicker">SIMULATED COSTS</span>
          <h2 id="fees-title">Trading platform costs</h2>
        </div>
      </div>
      <p className="muted">
        What your trading platform charges, so paper trading costs what real trading would. Each simulated trade pays the transaction fee and each
        withdrawal pays the withdrawal fee, in the portfolio's currency, on top of the strategy's slippage. Enter 0 if your platform charges nothing.
        A change applies to trades and withdrawals made from now on; earlier ones keep the fee they were charged.
      </p>
      {fees.loading && !fees.data ? <Loading /> : null}
      {fees.error ? <Notice tone="error" onRetry={fees.reload}>{fees.error}</Notice> : null}
      {fees.data ? (
        <form className="inline-form" onSubmit={(e) => void onSave(e)}>
          <label className="field">
            <span>Fee per transaction</span>
            <input inputMode="decimal" value={shownTrade} onChange={(e) => setTrade(e.target.value)} />
          </label>
          <label className="field">
            <span>Fee per withdrawal</span>
            <input inputMode="decimal" value={shownWithdrawal} onChange={(e) => setWithdrawal(e.target.value)} />
          </label>
          <button type="submit" className="secondary-button" disabled={save.running || !dirty}>
            {save.running ? "Saving…" : "Save costs"}
          </button>
        </form>
      ) : null}
      {problem ? <Notice tone="error">{problem}</Notice> : null}
      {save.error ? <Notice tone="error">{save.error}</Notice> : null}
      {save.result && !dirty ? <Notice tone="success">Saved. New trades and withdrawals use these fees.</Notice> : null}
    </section>
  );
}
