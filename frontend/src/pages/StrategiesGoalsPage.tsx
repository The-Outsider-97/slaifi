import { useEffect, useState, type FormEvent } from "react";

import { AppShell } from "../components/AppShell";
import { Empty, Loading, Notice } from "../components/finance/Notice";
import { PageHeading } from "../components/finance/PageHeading";
import { useAction, useAsync } from "../hooks/useAsync";
import { humanize, money, percent } from "../lib/format";
import {
  activateStrategy,
  analyzeGoal,
  createGoal,
  createStrategy,
  deleteGoal,
  deleteStrategy,
  fetchGoals,
  fetchStrategies,
  listPortfolios,
  updateStrategy,
} from "../services/finance";
import type { Goal, Strategy } from "../types/finance";

const RISK = ["conservative", "moderate", "aggressive"];

/** Fraction fields are edited as percentages and sent as fractions. */
const PERCENT_FIELDS: { key: keyof Strategy; label: string; hard: boolean; help: string }[] = [
  { key: "max_position_weight", label: "Max single position", hard: true, help: "Largest share of the portfolio one holding may reach." },
  { key: "max_drawdown_rate", label: "Max drawdown", hard: true, help: "Portfolio loss from its peak that you will not accept." },
  { key: "cash_reserve_rate", label: "Cash reserve", hard: true, help: "Share kept in cash and never invested or withdrawn." },
  { key: "max_annualized_volatility", label: "Max volatility", hard: true, help: "Annualised volatility cap for a single instrument." },
];

function toPercentText(rate: number | null): string {
  return rate === null || rate === undefined ? "" : String(Number((rate * 100).toFixed(4)));
}

function StrategyEditor({ strategy, active, onChanged }: { strategy: Strategy; active: boolean; onChanged: () => void }) {
  const [risk, setRisk] = useState(strategy.risk_tolerance);
  const [horizon, setHorizon] = useState(String(strategy.horizon_days));
  const [percentValues, setPercentValues] = useState<Record<string, string>>(
    Object.fromEntries(PERCENT_FIELDS.map((f) => [f.key, toPercentText(strategy[f.key] as number | null)])),
  );
  const [excluded, setExcluded] = useState(strategy.excluded_symbols.join(", "));
  const [prohibited, setProhibited] = useState(strategy.prohibited_asset_classes.join(", "));
  const [ack, setAck] = useState(false);
  const [needsAck, setNeedsAck] = useState(false);
  const [saved, setSaved] = useState(false);
  const update = useAction(updateStrategy);
  const activate = useAction(activateStrategy);
  const remove = useAction(deleteStrategy);

  // When the saved strategy changes (after a save or a reload), show the stored values.
  useEffect(() => {
    setRisk(strategy.risk_tolerance);
    setHorizon(String(strategy.horizon_days));
    setPercentValues(Object.fromEntries(PERCENT_FIELDS.map((f) => [f.key, toPercentText(strategy[f.key] as number | null)])));
    setExcluded(strategy.excluded_symbols.join(", "));
    setProhibited(strategy.prohibited_asset_classes.join(", "));
  }, [strategy]);

  const changes = (): Record<string, unknown> => {
    const out: Record<string, unknown> = {};
    if (risk !== strategy.risk_tolerance) out.risk_tolerance = risk;
    if (Number(horizon) !== strategy.horizon_days && Number(horizon) > 0) out.horizon_days = Number(horizon);
    for (const f of PERCENT_FIELDS) {
      const before = toPercentText(strategy[f.key] as number | null);
      const now = percentValues[f.key]?.trim() ?? "";
      if (now !== before) out[f.key] = now === "" ? null : Number(now) / 100;
    }
    const list = (text: string) => text.split(",").map((s) => s.trim()).filter(Boolean);
    if (excluded.trim() !== strategy.excluded_symbols.join(", ")) out.excluded_symbols = list(excluded.toUpperCase());
    if (prohibited.trim() !== strategy.prohibited_asset_classes.join(", ")) out.prohibited_asset_classes = list(prohibited.toLowerCase());
    return out;
  };
  const pending = changes();
  const dirty = Object.keys(pending).length > 0;

  const save = async () => {
    setSaved(false);
    const done = await update.run(strategy.strategy_id, pending, ack);
    if (done) {
      setSaved(true);
      setNeedsAck(false);
      setAck(false);
      onChanged();
    } else {
      setNeedsAck(true);
    }
  };

  return (
    <div className="stack">
      <div className="form-grid">
        <label className="field">
          <span>Risk tolerance</span>
          <select value={risk} onChange={(e) => setRisk(e.target.value)}>
            {RISK.map((r) => <option key={r} value={r}>{humanize(r)}</option>)}
          </select>
        </label>
        <label className="field">
          <span>Horizon (days)</span>
          <input inputMode="numeric" value={horizon} onChange={(e) => setHorizon(e.target.value)} />
        </label>
        {PERCENT_FIELDS.map((f) => (
          <label className="field" key={f.key}>
            <span>{f.label} (%){f.hard ? " · hard limit" : ""}</span>
            <input
              inputMode="decimal"
              value={percentValues[f.key]}
              onChange={(e) => setPercentValues({ ...percentValues, [f.key]: e.target.value })}
              aria-describedby={`help-${strategy.strategy_id}-${f.key}`}
              placeholder="no limit"
            />
            <small id={`help-${strategy.strategy_id}-${f.key}`}>{f.help}</small>
          </label>
        ))}
        <label className="field">
          <span>Never buy (symbols)</span>
          <input value={excluded} onChange={(e) => setExcluded(e.target.value)} placeholder="TSLA, NVDA" />
        </label>
        <label className="field">
          <span>Prohibited asset classes</span>
          <input value={prohibited} onChange={(e) => setProhibited(e.target.value)} placeholder="crypto, forex" />
        </label>
      </div>

      {needsAck && update.error ? (
        <label className="check">
          <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
          <span>I understand this loosens a hard limit, and I want to proceed.</span>
        </label>
      ) : null}
      {update.error ? <Notice tone="error">{update.error}</Notice> : null}
      {saved ? <Notice tone="success">Strategy saved.</Notice> : null}
      {activate.error ? <Notice tone="error">{activate.error}</Notice> : null}
      {remove.error ? <Notice tone="error">{remove.error}</Notice> : null}

      <div className="button-row">
        <button type="button" className="primary-cta primary-cta--inline" disabled={!dirty || update.running} onClick={() => void save()}>
          {update.running ? "Saving…" : "Save changes"}
        </button>
        {!active ? (
          <button type="button" className="secondary-button" disabled={activate.running} onClick={async () => { if (await activate.run(strategy.strategy_id)) onChanged(); }}>
            Make active
          </button>
        ) : null}
        {!active ? (
          <button type="button" className="secondary-button secondary-button--danger" disabled={remove.running} onClick={async () => { if (await remove.run(strategy.strategy_id)) onChanged(); }}>
            Delete
          </button>
        ) : null}
      </div>
    </div>
  );
}

function Strategies() {
  const [version, setVersion] = useState(0);
  const [name, setName] = useState("");
  const [preset, setPreset] = useState("");
  const data = useAsync((signal) => fetchStrategies(signal), `s|${version}`);
  const create = useAction(createStrategy);
  const [openId, setOpenId] = useState<string | null>(null);
  const refresh = () => setVersion((v) => v + 1);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const made = await create.run({ name: name.trim(), preset_id: preset || null });
    if (made) {
      setName("");
      setOpenId(made.strategy_id);
      refresh();
    }
  };

  return (
    <section className="panel analysis-panel" aria-labelledby="strategies-title">
      <div className="panel-heading">
        <div>
          <span className="section-kicker">HOW YOU INVEST</span>
          <h2 id="strategies-title">Strategies</h2>
        </div>
      </div>
      {data.loading && !data.data ? <Loading /> : null}
      {data.error ? <Notice tone="error" onRetry={data.reload}>{data.error}</Notice> : null}
      {data.data ? (
        <div className="stack">
          <p className="muted">{data.data.note} Hard limits always win over preferences: a trade that breaks one is rejected.</p>
          {data.data.strategies.map((s) => {
            const active = s.strategy_id === data.data?.active_strategy_id;
            const open = openId === s.strategy_id;
            return (
              <article className="strategy-card" key={s.strategy_id}>
                <header>
                  <div>
                    <strong>{s.name}</strong>{" "}
                    {active ? <span className="status-badge status-badge--dca">ACTIVE</span> : null}
                    <small className="block">
                      {s.preset ? `Started from “${humanize(s.preset)}” · ` : "Custom · "}
                      {humanize(s.risk_tolerance)} · {s.horizon_days}-day horizon · max position {percent(s.max_position_weight, 0)}
                    </small>
                  </div>
                  <button type="button" className="secondary-button" aria-expanded={open} onClick={() => setOpenId(open ? null : s.strategy_id)}>
                    {open ? "Close" : "Edit"}
                  </button>
                </header>
                {open ? <StrategyEditor key={s.strategy_id} strategy={s} active={active} onChanged={refresh} /> : null}
              </article>
            );
          })}

          <form className="inline-form" onSubmit={submit}>
            <label className="field field--grow">
              <span>New strategy name</span>
              <input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} />
            </label>
            <label className="field field--compact">
              <span>Start from</span>
              <select value={preset} onChange={(e) => setPreset(e.target.value)}>
                <option value="">Default</option>
                {data.data.presets.map((p) => (
                  <option key={p.preset ?? p.strategy_id} value={p.preset ?? ""}>{p.name}</option>
                ))}
              </select>
            </label>
            <button className="secondary-button" type="submit" disabled={create.running || !name.trim()}>Create</button>
          </form>
          {create.error ? <Notice tone="error">{create.error}</Notice> : null}
        </div>
      ) : null}
    </section>
  );
}

function GoalCard({ goal, portfolioId, onDeleted }: { goal: Goal; portfolioId: string | null; onDeleted: () => void }) {
  const [rate, setRate] = useState("");
  const analyze = useAction(analyzeGoal);
  const remove = useAction(deleteGoal);
  const report = analyze.result;

  const run = () => {
    const assumed = rate.trim() === "" ? null : Number(rate) / 100;
    void analyze.run(goal.goal_id, { assumed_annual_return_rate: assumed, portfolio_id: portfolioId ?? goal.portfolio_id });
  };

  return (
    <article className="strategy-card">
      <header>
        <div>
          <strong>{goal.name}</strong>
          <small className="block">
            {humanize(goal.basis)}
            {goal.target_amount ? ` · ${money(goal.target_amount, goal.currency)}${goal.period ? ` ${goal.period}` : ""}` : ""}
            {goal.target_annual_rate !== null ? ` · ${percent(goal.target_annual_rate, 1)} a year` : ""}
            {goal.horizon_years ? ` · ${goal.horizon_years} years` : ""}
          </small>
        </div>
        <button type="button" className="secondary-button secondary-button--danger" disabled={remove.running} onClick={async () => { if (await remove.run(goal.goal_id)) onDeleted(); }}>
          Delete
        </button>
      </header>
      <div className="inline-form">
        <label className="field field--compact">
          <span>Assumed yearly return (%) — optional</span>
          <input inputMode="decimal" value={rate} onChange={(e) => setRate(e.target.value)} placeholder="e.g. 6" />
        </label>
        <button type="button" className="secondary-button" disabled={analyze.running} onClick={run}>
          {analyze.running ? "Analysing…" : "Analyse feasibility"}
        </button>
      </div>
      {analyze.error ? <Notice tone="error">{analyze.error}</Notice> : null}
      {remove.error ? <Notice tone="error">{remove.error}</Notice> : null}
      {report ? (
        <div className="stack" data-testid="goal-report">
          <dl className="facts">
            <div><dt>Status</dt><dd>{humanize(report.status)}</dd></div>
            <div><dt>Return needed</dt><dd>{percent(report.required_annual_return_rate)}</dd><small>per year, on {money(report.capital_used)}</small></div>
            <div><dt>Capital needed</dt><dd>{money(report.required_capital_at_assumed_rate)}</dd><small>{report.assumed_annual_return_rate === null ? "set an assumed return" : `at ${percent(report.assumed_annual_return_rate, 1)}`}</small></div>
          </dl>
          {report.progress ? (
            <p>
              Progress ({report.progress.window}): {money(report.progress.measured_amount)}
              {report.progress.target_amount ? ` of ${money(report.progress.target_amount)}` : ""}.{" "}
              {report.progress.detail}
            </p>
          ) : null}
          {report.scenarios.length ? (
            <table className="table" aria-label="Scenarios">
              <thead><tr><th>Scenario</th><th>Return</th><th>Result</th></tr></thead>
              <tbody>
                {report.scenarios.map((s) => (
                  <tr key={s.label}>
                    <th scope="row">{s.label}</th>
                    <td>{percent(s.annual_return_rate)} <small>({s.source})</small></td>
                    <td>{s.meets_target === null ? "—" : s.meets_target ? "Meets target" : `Short by ${money(s.shortfall)}`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          {report.findings.map((f) => (
            <p key={f.code} className={f.severity === "error" ? "negative-text" : "muted"}>{f.message}</p>
          ))}
          <small className="muted">{report.disclaimer}</small>
        </div>
      ) : null}
    </article>
  );
}

const GOAL_KINDS: { id: string; label: string; fields: ("amount" | "period" | "rate" | "years" | "capital")[] }[] = [
  { id: "income", label: "Regular income", fields: ["amount", "period", "capital"] },
  { id: "return", label: "Annual return", fields: ["rate", "capital"] },
  { id: "growth", label: "Growth over years", fields: ["rate", "years", "capital"] },
];

function NewGoal({ onCreated }: { onCreated: () => void }) {
  const [kind, setKind] = useState("income");
  const [basis, setBasis] = useState("realized_profit");
  const [name, setName] = useState("");
  const [amount, setAmount] = useState("");
  const [period, setPeriod] = useState("monthly");
  const [rate, setRate] = useState("");
  const [years, setYears] = useState("");
  const [capital, setCapital] = useState("");
  const create = useAction(createGoal);
  const fields = GOAL_KINDS.find((k) => k.id === kind)?.fields ?? [];

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const body: Record<string, unknown> = { name: name.trim() };
    body.basis = kind === "income" ? basis : "total_return";
    if (fields.includes("amount") && amount) body.target_amount = amount;
    if (fields.includes("period")) body.period = period;
    if (fields.includes("rate") && rate) body.target_annual_rate = Number(rate) / 100;
    if (fields.includes("years") && years) body.horizon_years = Number(years);
    if (capital) body.starting_capital = capital;
    const made = await create.run(body);
    if (made) {
      setName("");
      setAmount("");
      setRate("");
      setYears("");
      onCreated();
    }
  };

  return (
    <form className="stack" onSubmit={submit} aria-label="New goal">
      <div className="form-grid">
        <label className="field">
          <span>Goal type</span>
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            {GOAL_KINDS.map((k) => <option key={k.id} value={k.id}>{k.label}</option>)}
          </select>
        </label>
        <label className="field">
          <span>Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} placeholder="e.g. $200 a month" required />
        </label>
        {kind === "income" ? (
          <label className="field">
            <span>Counts</span>
            <select value={basis} onChange={(e) => setBasis(e.target.value)}>
              <option value="realized_profit">Profit from selling</option>
              <option value="investment_income">Dividends and interest</option>
              <option value="total_return">Total return</option>
            </select>
          </label>
        ) : null}
        {fields.includes("amount") ? (
          <label className="field">
            <span>Target amount (USD)</span>
            <input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} required />
          </label>
        ) : null}
        {fields.includes("period") ? (
          <label className="field">
            <span>Per</span>
            <select value={period} onChange={(e) => setPeriod(e.target.value)}>
              {["daily", "weekly", "monthly", "quarterly", "annual"].map((p) => <option key={p} value={p}>{humanize(p)}</option>)}
            </select>
          </label>
        ) : null}
        {fields.includes("rate") ? (
          <label className="field">
            <span>Target return per year (%)</span>
            <input inputMode="decimal" value={rate} onChange={(e) => setRate(e.target.value)} required />
          </label>
        ) : null}
        {fields.includes("years") ? (
          <label className="field">
            <span>Over (years)</span>
            <input inputMode="decimal" value={years} onChange={(e) => setYears(e.target.value)} />
          </label>
        ) : null}
        <label className="field">
          <span>Starting capital (USD, optional)</span>
          <input inputMode="decimal" value={capital} onChange={(e) => setCapital(e.target.value)} />
        </label>
      </div>
      <p className="muted">A target is an objective, not a guarantee. SLAIFI reports what return it would take and whether that is consistent with your limits.</p>
      {create.error ? <Notice tone="error">{create.error}</Notice> : null}
      <button className="primary-cta primary-cta--inline" type="submit" disabled={create.running || !name.trim()}>
        {create.running ? "Saving…" : "Add goal"}
      </button>
    </form>
  );
}

function Goals() {
  const [version, setVersion] = useState(0);
  const goals = useAsync((signal) => fetchGoals(signal), `g|${version}`);
  const portfolios = useAsync((signal) => listPortfolios(signal), "list");
  const [portfolioId, setPortfolioId] = useState("");
  const refresh = () => setVersion((v) => v + 1);

  return (
    <section className="panel analysis-panel" aria-labelledby="goals-title">
      <div className="panel-heading">
        <div>
          <span className="section-kicker">WHAT YOU WANT</span>
          <h2 id="goals-title">Goals</h2>
        </div>
      </div>
      <div className="stack">
        <label className="field field--compact">
          <span>Measure progress against</span>
          <select value={portfolioId} onChange={(e) => setPortfolioId(e.target.value)}>
            <option value="">Goal's own portfolio, if any</option>
            {(portfolios.data?.portfolios ?? []).map((p) => <option key={p.portfolio_id} value={p.portfolio_id}>{p.name}</option>)}
          </select>
        </label>
        {goals.loading && !goals.data ? <Loading /> : null}
        {goals.error ? <Notice tone="error" onRetry={goals.reload}>{goals.error}</Notice> : null}
        {goals.data && goals.data.goals.length === 0 ? <Empty title="No goals yet">Add one below, or describe it to the SLAI Advisor.</Empty> : null}
        {goals.data?.goals.map((g) => (
          <GoalCard key={g.goal_id} goal={g} portfolioId={portfolioId || null} onDeleted={refresh} />
        ))}
        <details className="disclosure" open={goals.data?.goals.length === 0}>
          <summary>Add a goal</summary>
          <NewGoal onCreated={refresh} />
        </details>
      </div>
    </section>
  );
}

export function StrategiesGoalsPage() {
  return (
    <AppShell currentPage="strategy">
      <main className="dashboard dashboard--finance" id="strategies-goals">
        <PageHeading
          kicker="YOUR RULES AND YOUR TARGETS"
          title="Strategies & goals"
          subtitle="Set the limits you will not cross, then see what your goals would actually require."
        />
        <div className="dashboard-grid dashboard-grid--secondary">
          <Strategies />
          <Goals />
        </div>
      </main>
    </AppShell>
  );
}
