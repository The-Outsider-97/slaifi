import { useState } from "react";
import type { FormEvent } from "react";

import { useAction, useAsync } from "../../hooks/useAsync";
import { dateTime, humanize, money, percent, shortDate, signedPercent } from "../../lib/format";
import {
  checkAgent,
  fetchAgents,
  fetchAllocation,
  fetchLearningMemory,
  searchKnowledge,
  setAgentEnabled,
  shareWithSlai,
} from "../../services/finance";
import type { AgentStatus, AllocationSuggestion, KnowledgeAnswer, LearningRecall, LearningShare } from "../../types/finance";
import { Empty, Loading, Notice, Simulated } from "./Notice";

/** What a person should read for each state. "Off" is the normal state: nothing here is forced. */
export function agentStateText(agent: AgentStatus): { text: string; tone: "ok" | "warn" | "off" } {
  if (!agent.enabled || agent.state === "disabled") return { text: "Off", tone: "off" };
  switch (agent.state) {
    case "ready":
      return { text: "On and working", tone: "ok" };
    case "unavailable":
      return { text: "On, but SLAI could not run it", tone: "warn" };
    case "untested":
      return { text: "On (not used yet)", tone: "off" };
    default:
      return { text: humanize(agent.state), tone: "warn" };
  }
}

type SwitchRowProps = {
  agent: AgentStatus;
  busy: boolean;
  onToggle: (enabled: boolean) => void;
  onCheck: () => void;
};

export function AgentSwitchRow({ agent, busy, onToggle, onCheck }: SwitchRowProps) {
  const state = agentStateText(agent);
  return (
    <li className="agent-row" data-testid={`agent-${agent.name}`}>
      <div className="agent-row__text">
        <strong>{agent.label}</strong>
        <span className="muted">{agent.purpose}</span>
        <span className={state.tone === "ok" ? "positive-text" : state.tone === "warn" ? "negative-text" : "muted"}>{state.text}</span>
        {agent.enabled && agent.detail ? <small className="muted">{agent.detail}</small> : null}
      </div>
      <div className="agent-row__actions">
        <label className="toggle">
          <input type="checkbox" role="switch" checked={agent.enabled} disabled={busy} onChange={(e) => onToggle(e.target.checked)} />
          <span>{agent.enabled ? "On" : "Off"}</span>
        </label>
        {agent.enabled ? (
          <button type="button" className="secondary-button" disabled={busy} onClick={onCheck}>
            Check
          </button>
        ) : null}
      </div>
    </li>
  );
}

/** Settings card: one switch per optional SLAI agent. Everything starts off. */
export function AgentSwitchesCard() {
  const agents = useAsync((signal) => fetchAgents(signal), "agents");
  const toggle = useAction(setAgentEnabled);
  const check = useAction(checkAgent);
  const busy = toggle.running || check.running;

  const change = async (name: string, enabled: boolean) => {
    if (await toggle.run(name, enabled)) agents.reload();
  };
  const test = async (name: string) => {
    if (await check.run(name)) agents.reload();
  };

  return (
    <section className="panel analysis-panel" aria-labelledby="agents-title" data-testid="agent-switches">
      <div className="panel-heading">
        <div>
          <span className="section-kicker">OPTIONAL SLAI AGENTS</span>
          <h2 id="agents-title">Extra help from SLAI</h2>
        </div>
      </div>
      {agents.loading && !agents.data ? <Loading /> : null}
      {agents.error ? <Notice tone="error" onRetry={agents.reload}>{agents.error}</Notice> : null}
      {toggle.error ? <Notice tone="error">{toggle.error}</Notice> : null}
      {check.error ? <Notice tone="error">{check.error}</Notice> : null}
      {agents.data ? (
        <>
          <p className="muted">{agents.data.note}</p>
          <ul className="agent-list">
            {agents.data.agents.map((a) => (
              <AgentSwitchRow key={a.name} agent={a} busy={busy} onToggle={(on) => void change(a.name, on)} onCheck={() => void test(a.name)} />
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}

// ------------------------------------------------------------------------- knowledge
export function KnowledgeResults({ answer, query }: { answer: KnowledgeAnswer; query: string }) {
  if (answer.status === "disabled") {
    return (
      <Notice tone="info" title="The Knowledge agent is off">
        Switch it on under <a href="#/settings">Settings</a> to look things up in SLAIFI's own documentation.
      </Notice>
    );
  }
  if (answer.status === "unavailable") {
    return <Notice tone="warning" title="NOT AVAILABLE">{answer.detail ?? "SLAI's Knowledge agent could not be reached."}</Notice>;
  }
  if (answer.status !== "ok" || answer.passages.length === 0) {
    return <Empty title="Nothing found">SLAIFI's documentation has nothing that matches “{query}”.</Empty>;
  }
  return (
    <ol className="knowledge-results" aria-label="Documentation passages">
      {answer.passages.map((p, i) => (
        <li key={`${p.source}-${i}`}>
          <strong>{p.heading ?? "Untitled section"}</strong>
          <small className="muted">{p.source}</small>
          <p>{p.text}</p>
        </li>
      ))}
    </ol>
  );
}

/** Looks only in SLAIFI's own documentation. It never reads your data or the web. */
export function KnowledgeLookup() {
  const [text, setText] = useState("");
  const [asked, setAsked] = useState("");
  const search = useAction((q: string) => searchKnowledge(q));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const q = text.trim();
    if (q.length < 2) return;
    setAsked(q);
    await search.run(q);
  };

  return (
    <section className="panel analysis-panel" aria-labelledby="knowledge-title" data-testid="knowledge-lookup">
      <div className="panel-heading">
        <div>
          <span className="section-kicker">OPTIONAL · SLAI KNOWLEDGE AGENT</span>
          <h2 id="knowledge-title">Look something up</h2>
        </div>
      </div>
      <p className="muted">Searches SLAIFI's own documentation (how recommendations, limits and short selling work). It does not read your portfolio or the web.</p>
      <form className="inline-form" onSubmit={submit}>
        <label className="field field--compact">
          <span>What do you want to know?</span>
          <input value={text} maxLength={200} onChange={(e) => setText(e.target.value)} placeholder="e.g. how does short selling work" />
        </label>
        <button className="secondary-button" type="submit" disabled={search.running || text.trim().length < 2}>
          {search.running ? "Looking…" : "Look up"}
        </button>
      </form>
      {search.running ? <Loading label="Searching the documentation…" /> : null}
      {search.error ? <Notice tone="error">{search.error}</Notice> : null}
      {search.result && !search.running ? <KnowledgeResults answer={search.result} query={asked} /> : null}
    </section>
  );
}

// ------------------------------------------------------------------------ allocation
const CHECK_LABEL: Record<string, string> = {
  finite: "Numbers are valid",
  position_bounds: "Each position within its limits",
  budget: "Adds up to the investable amount",
  volatility_cap: "Within the strategy's volatility limit",
  concentration: "Within the strategy's concentration limit",
};

export function AllocationView({ s, currency }: { s: AllocationSuggestion; currency: string }) {
  if (s.status === "disabled") {
    return (
      <Notice tone="info" title="The Optimization agent is off">
        Switch it on under <a href="#/settings">Settings</a> to see a suggested mix for this portfolio. Nothing changes until you place orders yourself.
      </Notice>
    );
  }
  const problem = s.status !== "ok";
  return (
    <div className="stack" data-testid="allocation-result">
      {problem ? (
        <Notice tone={s.status === "unavailable" ? "warning" : "info"} title={s.status === "unavailable" ? "NOT AVAILABLE" : humanize(s.status)}>
          {s.detail ?? "No suggestion could be made."}
        </Notice>
      ) : null}
      {s.status === "rejected" && s.checks.some((c) => !c.ok) ? (
        <ul className="check-list" aria-label="Checks that failed">
          {s.checks.filter((c) => !c.ok).map((c) => <li key={c.code} className="negative-text">{c.message}</li>)}
        </ul>
      ) : null}
      {s.status === "ok" ? (
        <>
          <table className="table" aria-label="Suggested allocation">
            <thead>
              <tr><th>Asset</th><th>Now</th><th>Suggested</th><th>Change</th><th>Amount to move</th></tr>
            </thead>
            <tbody>
              {s.lines.map((l) => (
                <tr key={l.symbol}>
                  <td>{l.display}</td>
                  <td>{percent(l.current_weight, 1)}</td>
                  <td>{percent(l.suggested_weight, 1)}</td>
                  <td className={l.change > 0 ? "positive-text" : l.change < 0 ? "negative-text" : undefined}>{signedPercent(l.change, 1)}</td>
                  <td>{l.amount === null ? "—" : money(l.amount, currency)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <dl className="settings-list">
            <div className="setting-row"><dt>Cash kept back</dt><dd>{s.cash_weight === null ? "—" : percent(s.cash_weight, 1)}</dd></div>
            <div className="setting-row"><dt>Volatility (past), now → suggested</dt><dd>{percent(s.current?.annual_volatility, 1)} → {percent(s.suggested?.annual_volatility, 1)}</dd></div>
            <div className="setting-row"><dt>Average yearly return (past), now → suggested</dt><dd>{signedPercent(s.current?.historical_annual_return, 1)} → {signedPercent(s.suggested?.historical_annual_return, 1)}</dd></div>
          </dl>
          <ul className="check-list" aria-label="Checks SLAIFI ran on the suggestion">
            {s.checks.map((c) => (
              <li key={c.code} className={c.ok ? "positive-text" : "negative-text"}>
                {c.ok ? "✓" : "✗"} {CHECK_LABEL[c.code] ?? humanize(c.code)}
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {s.excluded.length > 0 ? (
        <details>
          <summary>Left out ({s.excluded.length})</summary>
          <ul>{s.excluded.map((e) => <li key={e.symbol}><strong>{e.symbol}</strong>: {e.reason}</li>)}</ul>
        </details>
      ) : null}
      {s.status === "ok" || s.observations > 0 ? (
        <p className="muted">
          {s.basis}
          {s.window_start && s.window_end ? ` Window: ${shortDate(s.window_start)} to ${shortDate(s.window_end)}, ${s.observations} daily observations.` : ""}
          {s.solver ? ` Solver: ${s.solver}.` : ""}
          {s.generated_at ? ` Made ${dateTime(s.generated_at)}.` : ""} It is advice only: no order is placed.
        </p>
      ) : null}
    </div>
  );
}

/** Optional: a suggested mix for the selected paper portfolio, produced by SLAI's optimizer and re-checked by SLAIFI.
 *  It runs only when asked, because it reads price history for every holding. */
export function SuggestedAllocation({ id, currency }: { id: string; currency: string }) {
  const [focus, setFocus] = useState<"steadiest" | "strategy">("steadiest");
  const [watchlist, setWatchlist] = useState(false);
  const run = useAction(() => fetchAllocation(id, { focus, watchlist }));

  return (
    <section className="panel analysis-panel" aria-labelledby="alloc-title" data-testid="suggested-allocation">
      <div className="panel-heading">
        <div>
          <span className="section-kicker">OPTIONAL · SLAI OPTIMIZATION AGENT</span>
          <h2 id="alloc-title">Suggested allocation</h2>
        </div>
        <Simulated />
      </div>
      <p className="muted">
        Asks SLAI's optimizer for a mix of this portfolio's holdings that fits your strategy's limits, then SLAIFI checks the answer itself. It is advice
        only: nothing is bought or sold.
      </p>
      <div className="inline-form">
        <label className="field field--compact">
          <span>Aim for</span>
          <select value={focus} onChange={(e) => setFocus(e.target.value === "strategy" ? "strategy" : "steadiest")}>
            <option value="steadiest">The steadiest mix</option>
            <option value="strategy">Balance risk and return for my strategy</option>
          </select>
        </label>
        <label className="toggle">
          <input type="checkbox" checked={watchlist} onChange={(e) => setWatchlist(e.target.checked)} />
          <span>Also consider my watchlist</span>
        </label>
        <button type="button" className="secondary-button" disabled={run.running} onClick={() => void run.run()}>
          {run.running ? "Working…" : "Suggest a mix"}
        </button>
      </div>
      {run.running ? <Loading label="Working out a mix from real price history…" /> : null}
      {run.error ? <Notice tone="error">{run.error}</Notice> : null}
      {run.result && !run.running ? <AllocationView s={run.result} currency={currency} /> : null}
    </section>
  );
}

// -------------------------------------------------------------------------------- learning
export function LearningMemoryView({ share, recall }: { share: LearningShare | null; recall: LearningRecall | null }) {
  const off = (share ?? recall)?.status === "disabled";
  if (off) {
    return (
      <Notice tone="info" title="The Learning agent is off">
        Switch it on under <a href="#/settings">Settings</a> to share your measured results with SLAI's learning memory.
      </Notice>
    );
  }
  return (
    <div className="stack" data-testid="learning-memory-result">
      {share?.status === "unavailable" ? <Notice tone="warning" title="NOT AVAILABLE">{share.detail}</Notice> : null}
      {share?.status === "nothing_to_share" ? <Empty title="Nothing to share yet">{share.detail}</Empty> : null}
      {share?.status === "ok" ? (
        <Notice tone="success" title="Shared with SLAI">
          {`${share.sent} new, ${share.duplicates} already held${share.refused ? `, ${share.refused} refused by SLAI` : ""}.${share.detail ? ` ${share.detail}` : ""}`}
        </Notice>
      ) : null}
      {recall?.status === "unavailable" ? <Notice tone="warning" title="NOT AVAILABLE">{recall.detail}</Notice> : null}
      {recall?.status === "empty" ? <Empty title="Nothing recorded yet">{recall.detail}</Empty> : null}
      {recall?.status === "ok" ? (
        <table className="table" aria-label="What SLAI has recorded">
          <thead>
            <tr><th>Recommendation</th><th>Outcomes SLAI holds</th><th>Average move afterwards</th></tr>
          </thead>
          <tbody>
            {recall.by_action.map((a) => (
              <tr key={a.action}>
                <td>{humanize(a.action)}</td>
                <td>{a.count}</td>
                <td>{a.mean_forward_return === null ? "—" : signedPercent(a.mean_forward_return, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </div>
  );
}

/** Optional: copy SLAIFI's measured outcomes into SLAI's learning memory. SLAIFI's own learning does not read it back. */
export function LearningMemoryPanel() {
  const share = useAction(shareWithSlai);
  const recall = useAction(() => fetchLearningMemory());
  const [last, setLast] = useState<"share" | "recall" | null>(null);
  const busy = share.running || recall.running;

  return (
    <section className="panel analysis-panel" aria-labelledby="learn-mem-title" data-testid="learning-memory">
      <div className="panel-heading">
        <div>
          <span className="section-kicker">OPTIONAL · SLAI LEARNING AGENT</span>
          <h2 id="learn-mem-title">Share results with SLAI</h2>
        </div>
      </div>
      <p className="muted">
        Sends each recommendation that has been checked against real prices (what was advised and how the price moved afterwards) to SLAI's learning
        memory so SLAI's other agents can use it. It does not change this track record, your strategy or any recommendation.
      </p>
      <div className="button-row">
        <button type="button" className="secondary-button" disabled={busy} onClick={() => { setLast("share"); void share.run(); }}>
          {share.running ? "Sharing…" : "Share my results"}
        </button>
        <button type="button" className="secondary-button" disabled={busy} onClick={() => { setLast("recall"); void recall.run(); }}>
          {recall.running ? "Reading…" : "Show what SLAI has recorded"}
        </button>
      </div>
      {share.error ? <Notice tone="error">{share.error}</Notice> : null}
      {recall.error ? <Notice tone="error">{recall.error}</Notice> : null}
      {busy ? <Loading label="Asking SLAI…" /> : null}
      {!busy && (share.result || recall.result) ? (
        <LearningMemoryView share={last === "share" ? share.result : null} recall={last === "recall" ? recall.result : null} />
      ) : null}
    </section>
  );
}
