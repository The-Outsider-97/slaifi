import { useState } from "react";

import { useAction, useAsync } from "../../hooks/useAsync";
import { humanize, percent } from "../../lib/format";
import {
  fetchAdaptations,
  fetchTrackRecord,
  listPortfolios,
  refreshTrackRecord,
  updateStrategy,
} from "../../services/finance";
import type { AdaptationProposal, Strategy, TrackRecord } from "../../types/finance";
import { Explained } from "./Explained";
import { Loading, Notice } from "./Notice";

const VERDICT_TEXT: Record<TrackRecord["verdict"], string> = {
  insufficient_sample: "Too early to say",
  better_than_chance: "Better than a coin flip so far",
  no_clear_edge: "No clear edge over a coin flip",
  worse_than_chance: "Worse than a coin flip so far",
};

/** How SLAIFI's own past recommendations did against what real prices then did. */
export function TrackRecordPanel() {
  const [version, setVersion] = useState(0);
  const record = useAsync((signal) => fetchTrackRecord(signal), `tr|${version}`);
  const refresh = useAction(refreshTrackRecord);
  const data = refresh.result?.track_record ?? record.data;
  const note = refresh.result?.refresh;

  return (
    <section className="panel analysis-panel" aria-labelledby="track-title">
      <div className="panel-heading">
        <div>
          <span className="section-kicker">HOW RELIABLE HAS IT BEEN</span>
          <h2 id="track-title">Track record</h2>
        </div>
        <button
          type="button"
          className="secondary-button"
          disabled={refresh.running}
          onClick={async () => {
            if (await refresh.run()) setVersion((v) => v + 1);
          }}
        >
          {refresh.running ? "Checking…" : "Check results against real prices"}
        </button>
      </div>
      {record.loading && !data ? <Loading /> : null}
      {record.error ? <Notice tone="error" onRetry={record.reload}>{record.error}</Notice> : null}
      {refresh.error ? <Notice tone="error">{refresh.error}</Notice> : null}
      {data ? (
        <div className="stack" data-testid="track-record">
          <dl className="facts">
            <div><dt>Recommendations logged</dt><dd>{data.logged}</dd><small>{data.pending} waiting to be checked</small></div>
            <div>
              <dt>Decisive results</dt>
              <dd>{data.scored}</dd>
              <small>{data.scored < data.minimum_for_verdict ? `${data.minimum_for_verdict} needed before it means anything` : "enough to compare with chance"}</small>
            </div>
            <div>
              <dt>Hit rate</dt>
              <dd>{data.hit_rate === null ? "—" : percent(data.hit_rate, 0)}</dd>
              <small>
                {data.interval_low === null || data.interval_high === null
                  ? "nothing measured yet"
                  : `95% range ${percent(data.interval_low, 0)}–${percent(data.interval_high, 0)}`}
              </small>
            </div>
          </dl>
          <p><strong>{VERDICT_TEXT[data.verdict]}.</strong> {data.note}</p>
          {data.by_action.length ? (
            <table className="table" aria-label="Results by action">
              <thead><tr><th>Action</th><th>Checked</th><th>Right</th><th>Average move after</th></tr></thead>
              <tbody>
                {data.by_action.map((a) => (
                  <tr key={a.action}>
                    <th scope="row">{humanize(a.action)}</th>
                    <td>{a.scored}</td>
                    <td>{a.hits}</td>
                    <td>{a.mean_forward_return === null ? "—" : percent(a.mean_forward_return, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          {note ? (
            <p className="muted">
              Checked {note.evaluated} just now.
              {note.unchecked_symbols.length ? ` Real prices were not available for ${note.unchecked_symbols.join(", ")}, so those stay unchecked.` : ""}
              {note.notes.length ? ` ${note.notes.join(" ")}` : ""}
            </p>
          ) : null}
          <small className="muted">{data.method}</small>
        </div>
      ) : null}
    </section>
  );
}

const KIND_LABEL: Record<AdaptationProposal["kind"], string> = {
  tighten: "Tighten",
  align: "Match your goal",
  observation: "Worth knowing",
};

/** Suggested strategy changes from how a paper portfolio behaved. Nothing applies by itself. */
export function StrategySuggestions({ strategy, onApplied }: { strategy: Strategy; onApplied: () => void }) {
  const [portfolioId, setPortfolioId] = useState("");
  const [explain, setExplain] = useState(false);
  const portfolios = useAsync((signal) => listPortfolios(signal), "list");
  const check = useAction(fetchAdaptations);
  const apply = useAction(updateStrategy);
  const [applied, setApplied] = useState<string | null>(null);
  const result = check.result;

  return (
    <div className="stack" aria-label="Suggestions from your results">
      <div className="inline-form">
        <label className="field field--compact">
          <span>Look at this portfolio</span>
          <select value={portfolioId} onChange={(e) => setPortfolioId(e.target.value)}>
            <option value="">None (goals and track record only)</option>
            {(portfolios.data?.portfolios ?? []).map((p) => <option key={p.portfolio_id} value={p.portfolio_id}>{p.name}</option>)}
          </select>
        </label>
        <label className="check">
          <input type="checkbox" checked={explain} onChange={(e) => setExplain(e.target.checked)} />
          <span>Ask SLAI to review them</span>
        </label>
        <button
          type="button"
          className="secondary-button"
          disabled={check.running}
          onClick={() => {
            setApplied(null);
            void check.run(strategy.strategy_id, portfolioId || null, explain);
          }}
        >
          {check.running ? "Checking…" : "Check suggestions"}
        </button>
      </div>
      {check.error ? <Notice tone="error">{check.error}</Notice> : null}
      {apply.error ? <Notice tone="error">{apply.error}</Notice> : null}
      {applied ? <Notice tone="success">{applied}</Notice> : null}
      {result ? (
        <div className="stack" data-testid="suggestions">
          {result.proposals.length === 0 ? <p className="muted">Nothing to suggest from the evidence available.</p> : null}
          {result.proposals.map((p) => (
            <article key={p.code} className="strategy-card">
              <header>
                <div>
                  <strong>{p.title}</strong> <span className="status-badge status-badge--dca">{KIND_LABEL[p.kind]}</span>
                  <small className="block">{p.rationale}</small>
                </div>
                {p.change ? (
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={apply.running}
                    onClick={async () => {
                      const done = await apply.run(strategy.strategy_id, p.change ?? {}, false);
                      if (done) {
                        setApplied(`Applied: ${p.title}.`);
                        onApplied();
                      }
                    }}
                  >
                    Apply
                  </button>
                ) : null}
              </header>
              <ul className="muted">
                {p.evidence.map((e) => <li key={e}>{e}</li>)}
                {p.change ? <li>Would change: {Object.entries(p.change).map(([k, v]) => `${humanize(k)} → ${String(v)}`).join(", ")}</li> : null}
              </ul>
            </article>
          ))}
          {result.notes.map((n) => <small key={n} className="muted">{n}</small>)}
          {result.explanation ? <Explained explanation={result.explanation} /> : null}
        </div>
      ) : null}
    </div>
  );
}
