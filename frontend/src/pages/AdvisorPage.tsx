import { useState, type FormEvent } from "react";

import { AppShell } from "../components/AppShell";
import { Explained } from "../components/finance/Explained";
import { Loading, Notice } from "../components/finance/Notice";
import { OutcomeDetails } from "../components/finance/OrderTicket";
import { PageHeading } from "../components/finance/PageHeading";
import { useAction, useAsync } from "../hooks/useAsync";
import { dateTime, humanize, money, percent } from "../lib/format";
import { confirmProposal, interpretInstruction, listPortfolios, rejectProposal } from "../services/finance";
import type { AdvisorChange, AdvisorResponse } from "../types/finance";

const EXAMPLES = [
  "Make this more conservative and keep any single position under 8%.",
  "I want to make $200 a month from my portfolio.",
  "Never buy crypto.",
  "For now, treat me as an aggressive investor — just for this session.",
  "Buy $500 of KO.",
];

function show(value: unknown): string {
  if (value === null || value === undefined || value === "") return "none";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(4);
  if (Array.isArray(value)) return value.length ? value.join(", ") : "none";
  return String(value);
}

function ChangeTable({ title, changes }: { title: string; changes: AdvisorChange[] }) {
  if (!changes.length) return null;
  return (
    <div>
      <h3>{title}</h3>
      <table className="table" aria-label={title}>
        <thead>
          <tr><th>Setting</th><th>Now</th><th>Proposed</th><th>Notes</th></tr>
        </thead>
        <tbody>
          {changes.map((c) => (
            <tr key={c.index}>
              <th scope="row">{humanize(c.field)}</th>
              <td>{show(c.old)}</td>
              <td><strong>{show(c.new)}</strong></td>
              <td>
                {c.hard_limit ? <span className="status-badge status-badge--review-risk">HARD LIMIT</span> : null}{" "}
                {c.loosens_limit ? <span className="status-badge status-badge--review-risk">LOOSENS A LIMIT</span> : null}{" "}
                {c.description}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Result({ result, portfolioId, onDone }: { result: AdvisorResponse; portfolioId: string | null; onDone: () => void }) {
  const [limits, setLimits] = useState(false);
  const [contradictions, setContradictions] = useState(false);
  const confirm = useAction(confirmProposal);
  const reject = useAction(rejectProposal);
  const proposal = result.proposal;

  const needLimits = result.needs_acknowledgement_of_limits && !limits;
  const needContradictions = result.needs_acknowledgement_of_contradictions && !contradictions;
  const blocked = result.blocked;

  const applied = confirm.result;
  const rejected = reject.result;

  if (applied) {
    return (
      <section className="panel analysis-panel" aria-labelledby="applied-title">
        <h2 id="applied-title">Applied</h2>
        <Notice tone="success" title="Your confirmation was recorded.">
          Changes were saved and the audit log was updated.
        </Notice>
        {applied.applied_changes.length ? (
          <ul className="plain-list">
            {applied.applied_changes.map((c) => <li key={c}>{c}</li>)}
          </ul>
        ) : null}
        {applied.created_goal_ids.length ? <p>{applied.created_goal_ids.length} goal(s) created.</p> : null}
        {applied.orders.map((o, i) => (
          <OutcomeDetails key={i} outcome={o} currency={o.portfolio?.currency ?? "USD"} />
        ))}
        <button type="button" className="secondary-button" onClick={onDone}>Start over</button>
      </section>
    );
  }
  if (rejected) {
    return (
      <section className="panel analysis-panel">
        <Notice tone="info" title="Proposal discarded">Nothing was changed.</Notice>
        <button type="button" className="secondary-button" onClick={onDone}>Start over</button>
      </section>
    );
  }

  return (
    <section className="panel analysis-panel" aria-labelledby="result-title" data-testid="advisor-result">
      <div className="panel-heading">
        <div>
          <span className="section-kicker">WHAT SLAIFI UNDERSTOOD</span>
          <h2 id="result-title">Proposal — nothing has changed yet</h2>
        </div>
      </div>

      <div className="stack">
        {result.blocked ? (
          <Notice tone="error" title="This request was blocked by SLAI's safety review">
            {(result.safety?.blockers ?? []).join(" ") || "The request cannot be processed."}
          </Notice>
        ) : null}
        {result.safety && !result.safety.available ? (
          <Notice tone="warning">SLAI's safety review is not available right now; SLAIFI's own limits still apply to everything below.</Notice>
        ) : null}
        {result.safety?.warnings.map((w) => <Notice key={w} tone="warning">{w}</Notice>)}
        {result.unrecognised && !result.blocked ? (
          <Notice tone="warning" title="I could not turn that into a change">
            Try one of the examples, or use the Strategies &amp; goals page to edit settings directly.
          </Notice>
        ) : null}

        {result.understood.length ? (
          <div>
            <h3>Understood</h3>
            <ul className="plain-list">{result.understood.map((u) => <li key={u}>{u}</li>)}</ul>
          </div>
        ) : null}

        {result.contradictions.map((c) => (
          <Notice key={c.description} tone="warning" title="Contradiction">{c.description}</Notice>
        ))}

        <ChangeTable title="Saved strategy changes (persistent)" changes={result.changes} />
        <ChangeTable title="Temporary for this analysis only" changes={result.temporary_changes} />
        {result.temporary_analysis ? (
          <Notice tone="info" title="Effect of the temporary change">
            {result.temporary_analysis.description}
            {result.temporary_analysis.new_findings.length ? ` New issues: ${result.temporary_analysis.new_findings.join(" ")}` : ""}
            {result.temporary_analysis.resolved_findings.length ? ` Resolved: ${result.temporary_analysis.resolved_findings.join(" ")}` : ""}
          </Notice>
        ) : null}

        {result.goals.map((g) => (
          <div key={g.name} className="advisor-card">
            <h3>Goal: {g.name}</h3>
            {g.error ? <Notice tone="error">{g.error}</Notice> : null}
            {g.report ? (
              <>
                <dl className="facts">
                  <div><dt>Status</dt><dd>{humanize(g.report.status)}</dd></div>
                  <div><dt>Return needed</dt><dd>{percent(g.report.required_annual_return_rate)}</dd><small>per year</small></div>
                  <div><dt>Capital assumed</dt><dd>{money(g.report.capital_used)}</dd></div>
                </dl>
                {g.report.findings.map((f) => <p key={f.code} className={f.severity === "error" ? "negative-text" : "muted"}>{f.message}</p>)}
                <small className="muted">{g.report.disclaimer}</small>
              </>
            ) : null}
          </div>
        ))}

        {result.orders.map((o, i) => (
          <div key={i} className="advisor-card">
            <h3>Simulated order: {o.draft.side} {o.draft.symbol ?? "?"}{o.draft.close_position ? " (close position)" : ""}</h3>
            {o.error ? <Notice tone="error">{o.error}</Notice> : null}
            {o.preview ? <OutcomeDetails outcome={o.preview} currency={o.preview.portfolio?.currency ?? "USD"} /> : null}
          </div>
        ))}

        {result.warnings.map((w) => <Notice key={w} tone="warning">{w}</Notice>)}
        <Explained explanation={result.explanation} />

        {proposal && result.requires_confirmation && !blocked ? (
          <div className="confirm-box" role="group" aria-label="Confirm or reject this proposal">
            <p>
              Nothing above is applied until you confirm. This proposal expires {dateTime(proposal.expires_at)}.
            </p>
            {result.needs_acknowledgement_of_limits ? (
              <label className="check">
                <input type="checkbox" checked={limits} onChange={(e) => setLimits(e.target.checked)} />
                <span>I understand this loosens a hard risk limit I set earlier.</span>
              </label>
            ) : null}
            {result.needs_acknowledgement_of_contradictions ? (
              <label className="check">
                <input type="checkbox" checked={contradictions} onChange={(e) => setContradictions(e.target.checked)} />
                <span>I have reviewed the contradictions above and still want to proceed.</span>
              </label>
            ) : null}
            <div className="button-row">
              <button
                type="button"
                className="primary-cta primary-cta--inline"
                disabled={confirm.running || needLimits || needContradictions}
                onClick={() => void confirm.run(proposal.proposal_id, { limits, contradictions })}
              >
                {confirm.running ? "Applying…" : "Confirm and apply"}
              </button>
              <button type="button" className="secondary-button" disabled={reject.running} onClick={() => void reject.run(proposal.proposal_id)}>
                Reject
              </button>
            </div>
            {confirm.error ? <Notice tone="error">{confirm.error}</Notice> : null}
            {reject.error ? <Notice tone="error">{reject.error}</Notice> : null}
          </div>
        ) : !result.unrecognised && !blocked ? (
          <Notice tone="info">There is nothing to confirm: this was informational only.</Notice>
        ) : null}

        <small className="muted">{result.disclaimer}{portfolioId ? "" : " No portfolio is selected, so order previews are unavailable."}</small>
      </div>
    </section>
  );
}

export function AdvisorPage() {
  const [text, setText] = useState("");
  const [portfolioId, setPortfolioId] = useState<string>("");
  const [result, setResult] = useState<AdvisorResponse | null>(null);
  const portfolios = useAsync((signal) => listPortfolios(signal), "list");
  const interpret = useAction(interpretInstruction);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!text.trim()) return;
    setResult(null);
    const out = await interpret.run(text.trim(), portfolioId || null, true);
    if (out) setResult(out);
  };

  const reset = () => {
    setResult(null);
    interpret.clear();
    setText("");
  };

  return (
    <AppShell currentPage="advisor">
      <main className="dashboard dashboard--finance" id="advisor">
        <PageHeading
          kicker="SAY WHAT YOU WANT"
          title="SLAI Advisor"
          subtitle="Describe a goal, a limit or a trade in plain words. You see exactly what would change before anything does."
        />

        <section className="panel analysis-panel" aria-labelledby="ask-title">
          <h2 id="ask-title" className="visually-hidden">Ask the advisor</h2>
          <form className="stack" onSubmit={submit}>
            <label className="field">
              <span>Your instruction</span>
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={3}
                maxLength={2000}
                placeholder="e.g. I want to make $50 a day, but never put more than 10% in one stock."
              />
            </label>
            <div className="chips" aria-label="Examples">
              {EXAMPLES.map((example) => (
                <button key={example} type="button" className="chip" onClick={() => setText(example)}>
                  {example}
                </button>
              ))}
            </div>
            <div className="inline-form">
              <label className="field field--compact">
                <span>Portfolio (for order previews and goals)</span>
                <select value={portfolioId} onChange={(e) => setPortfolioId(e.target.value)}>
                  <option value="">None</option>
                  {(portfolios.data?.portfolios ?? []).map((p) => (
                    <option key={p.portfolio_id} value={p.portfolio_id}>{p.name}</option>
                  ))}
                </select>
              </label>
              <button className="primary-cta primary-cta--inline" type="submit" disabled={interpret.running || !text.trim()}>
                {interpret.running ? "Interpreting…" : "Interpret"}
              </button>
            </div>
          </form>
          {interpret.running ? <Loading label="Understanding your request…" /> : null}
          {interpret.error ? <Notice tone="error">{interpret.error}</Notice> : null}
        </section>

        {result ? <Result result={result} portfolioId={portfolioId || null} onDone={reset} /> : null}
      </main>
    </AppShell>
  );
}
