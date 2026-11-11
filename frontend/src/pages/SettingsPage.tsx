import { AppShell } from "../components/AppShell";
import { Loading, Notice } from "../components/finance/Notice";
import { PageHeading } from "../components/finance/PageHeading";
import { useAction, useAsync } from "../hooks/useAsync";
import { useTheme } from "../hooks/useTheme";
import { dateTime, humanize } from "../lib/format";
import { fetchSlaiStatus } from "../services/api";
import { backupNow, fetchAudit, fetchSystemStatus, reconcileAll } from "../services/finance";

function Row({ label, value, tone }: { label: string; value: string; tone?: "ok" | "bad" | "warn" }) {
  return (
    <div className="setting-row">
      <dt>{label}</dt>
      <dd className={tone === "ok" ? "positive-text" : tone === "bad" ? "negative-text" : undefined}>{value}</dd>
    </div>
  );
}

export function SettingsPage() {
  const { theme, toggleTheme } = useTheme();
  const status = useAsync((signal) => fetchSystemStatus(signal), "status");
  const slai = useAsync((signal) => fetchSlaiStatus(signal), "slai");
  const audit = useAsync((signal) => fetchAudit(40, signal), "audit");
  const reconcile = useAction(reconcileAll);
  const backup = useAction(backupNow);

  const s = status.data;

  return (
    <AppShell currentPage="settings">
      <main className="dashboard dashboard--finance" id="settings">
        <PageHeading
          kicker="HOW SLAIFI IS RUNNING"
          title="Settings"
          subtitle="What data you are seeing, where it is kept, and whether it can be trusted."
        />

        <div className="dashboard-grid dashboard-grid--secondary">
          <section className="panel analysis-panel" aria-labelledby="runtime-title">
            <div className="panel-heading">
              <div>
                <span className="section-kicker">STATUS</span>
                <h2 id="runtime-title">Runtime</h2>
              </div>
              <button type="button" className="secondary-button" onClick={() => { status.reload(); slai.reload(); audit.reload(); }}>
                Refresh
              </button>
            </div>
            {status.loading && !s ? <Loading /> : null}
            {status.error ? <Notice tone="error" onRetry={status.reload}>{status.error}</Notice> : null}
            {s ? (
              <dl className="settings-list">
                <Row label="Market data" value={s.data_mode === "mock" ? "Mock (illustrative, not real prices)" : humanize(s.data_mode)} tone={s.data_mode === "mock" ? "warn" : "ok"} />
                <Row label="Provider" value={s.market_provider} />
                <Row label="Ledger storage" value={s.storage_status === "ok" ? "Healthy" : s.storage_status} tone={s.storage_status === "ok" ? "ok" : "bad"} />
                <Row label="Audit chain" value={s.audit_chain_intact ? "Intact" : `Broken${s.audit_chain_detail ? `: ${s.audit_chain_detail}` : ""}`} tone={s.audit_chain_intact ? "ok" : "bad"} />
                <Row label="Real-money trading" value="Unavailable — paper trading only" tone="ok" />
                <Row label="Orders on illustrative prices" value={s.paper_trading.allow_illustrative_execution ? "Allowed (labelled)" : "Refused"} />
                <Row label="Orders while market is closed" value={s.paper_trading.allow_closed_market_execution ? "Allowed" : "Refused"} />
                <Row label="Oldest quote an order may use" value={`${s.paper_trading.max_quote_age_seconds} seconds`} />
                <Row label="Write protection header" value={s.client_header_required ? "Required" : "Off"} />
              </dl>
            ) : null}
            {s && s.storage_status !== "ok" ? (
              <Notice tone="error" title="Order placement is disabled">
                The ledger failed its integrity check. Reads still work. Restore the database from a backup in the SLAIFI data folder, then restart.
              </Notice>
            ) : null}
            {s?.data_mode === "mock" ? (
              <Notice tone="warning" title="Illustrative data">
                A mock provider is configured. Prices, charts and simulated fills are not real market data. Set a market provider key to use real data.
              </Notice>
            ) : null}
          </section>

          <section className="panel analysis-panel" aria-labelledby="slai-title">
            <div className="panel-heading">
              <div>
                <span className="section-kicker">SLAI</span>
                <h2 id="slai-title">Reasoning runtime</h2>
              </div>
            </div>
            {slai.loading && !slai.data ? <Loading /> : null}
            {slai.error ? <Notice tone="error" onRetry={slai.reload}>{slai.error}</Notice> : null}
            {slai.data ? (
              <dl className="settings-list">
                <Row label="Status" value={humanize(slai.data.status)} tone={slai.data.status === "available" ? "ok" : slai.data.status === "disabled" ? undefined : "warn"} />
                <Row label="Agent" value={slai.data.agent ?? "—"} />
                <Row label="Version" value={slai.data.agent_version ?? "—"} />
              </dl>
            ) : null}
            {slai.data?.warnings.map((w) => <Notice key={w} tone="warning">{w}</Notice>)}
            <p className="muted">
              Recommendations, risk limits and ledger arithmetic are computed by SLAIFI's deterministic engines. SLAI only explains results and screens
              free-text requests; it cannot change a number or place a trade.
            </p>
          </section>
        </div>

        <div className="dashboard-grid dashboard-grid--secondary">
          <section className="panel analysis-panel" aria-labelledby="appearance-title">
            <div className="panel-heading">
              <div>
                <span className="section-kicker">DISPLAY</span>
                <h2 id="appearance-title">Appearance</h2>
              </div>
            </div>
            <label className="check">
              <input type="checkbox" checked={theme === "light"} onChange={toggleTheme} />
              <span>Use the light theme</span>
            </label>
          </section>

          <section className="panel analysis-panel" aria-labelledby="data-title">
            <div className="panel-heading">
              <div>
                <span className="section-kicker">YOUR DATA</span>
                <h2 id="data-title">Backup and checks</h2>
              </div>
            </div>
            <div className="stack">
              <div className="button-row">
                <button type="button" className="secondary-button" disabled={backup.running} onClick={() => void backup.run()}>
                  {backup.running ? "Backing up…" : "Back up now"}
                </button>
                <button type="button" className="secondary-button" disabled={reconcile.running} onClick={() => void reconcile.run()}>
                  {reconcile.running ? "Checking…" : "Reconcile all portfolios"}
                </button>
              </div>
              {backup.result ? <Notice tone="success" title="Backup written">{backup.result.backup}</Notice> : null}
              {backup.error ? <Notice tone="error">{backup.error}</Notice> : null}
              {reconcile.result ? (
                <Notice tone={reconcile.result.consistent ? "success" : "error"} title={reconcile.result.consistent ? "Everything agrees" : "Problems found"}>
                  {reconcile.result.consistent
                    ? `${reconcile.result.trade_count} trades and ${reconcile.result.cash_flow_count} cash flows reconcile; database integrity ${reconcile.result.database_integrity ?? "n/a"}.`
                    : reconcile.result.issues.map((i) => i.message).join(" ")}
                </Notice>
              ) : null}
              {reconcile.error ? <Notice tone="error">{reconcile.error}</Notice> : null}
            </div>
          </section>
        </div>

        <section className="panel analysis-panel" aria-labelledby="audit-title">
          <div className="panel-heading">
            <div>
              <span className="section-kicker">WHAT HAPPENED</span>
              <h2 id="audit-title">Audit log</h2>
            </div>
          </div>
          {audit.loading && !audit.data ? <Loading /> : null}
          {audit.error ? <Notice tone="error" onRetry={audit.reload}>{audit.error}</Notice> : null}
          {audit.data && audit.data.entries.length === 0 ? <p className="muted">No entries yet.</p> : null}
          {audit.data && audit.data.entries.length ? (
            <ol className="timeline" aria-label="Audit log">
              {audit.data.entries.map((e) => (
                <li key={e.seq}>
                  <time dateTime={e.at}>{dateTime(e.at)}</time>
                  <span><strong>{e.action}</strong> · {e.subject} <small>({e.actor})</small></span>
                </li>
              ))}
            </ol>
          ) : null}
        </section>
      </main>
    </AppShell>
  );
}
