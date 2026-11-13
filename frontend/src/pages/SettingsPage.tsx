import { AppShell } from "../components/AppShell";
import { AgentSwitchesCard } from "../components/finance/AgentPanels";
import { Loading, Notice } from "../components/finance/Notice";
import { PlatformFeesCard, ProviderKeyEditor } from "../components/finance/SettingsCards";
import { PageHeading } from "../components/finance/PageHeading";
import { useAction, useAsync } from "../hooks/useAsync";
import { useTheme } from "../hooks/useTheme";
import { dateTime, humanize } from "../lib/format";
import { fetchSlaiStatus } from "../services/api";
import { backupNow, checkProviders, fetchAudit, fetchProviderKeys, fetchProviders, fetchSystemStatus, reconcileAll } from "../services/finance";
import type { ProviderStatus } from "../types/finance";

function Row({ label, value, tone }: { label: string; value: string; tone?: "ok" | "bad" | "warn" }) {
  return (
    <div className="setting-row">
      <dt>{label}</dt>
      <dd className={tone === "ok" ? "positive-text" : tone === "bad" ? "negative-text" : undefined}>{value}</dd>
    </div>
  );
}

function providerState(p: ProviderStatus): { text: string; tone?: "ok" | "bad" | "warn" } {
  switch (p.state) {
    case "ready":
      return { text: p.last_success_at ? "Working" : "Ready (not used yet)", tone: "ok" };
    case "cooling_down":
      return { text: `Paused after an error${p.cooldown_until ? ` until ${dateTime(p.cooldown_until)}` : ""}`, tone: "warn" };
    case "rejected_credentials":
      return { text: "API key rejected", tone: "bad" };
    case "not_configured":
      return { text: "No key set", tone: undefined };
    default:
      return { text: humanize(p.state) };
  }
}

export function SettingsPage() {
  const { theme, toggleTheme } = useTheme();
  const status = useAsync((signal) => fetchSystemStatus(signal), "status");
  const slai = useAsync((signal) => fetchSlaiStatus(signal), "slai");
  const audit = useAsync((signal) => fetchAudit(40, signal), "audit");
  const providers = useAsync((signal) => fetchProviders(signal), "providers");
  const keys = useAsync((signal) => fetchProviderKeys(signal), "provider-keys");
  const check = useAction(checkProviders);
  const reconcile = useAction(reconcileAll);
  const backup = useAction(backupNow);

  const s = status.data;
  const keyFor = (name: string) => keys.data?.keys.find((k) => k.name === name);
  const keyChanged = () => {
    keys.reload();
    providers.reload();
    status.reload();
  };

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
                <Row
                  label="Market data sources"
                  value={
                    s.market_configured
                      ? `${s.market_providers.filter((p) => p.configured).length} of ${s.market_providers.length} configured`
                      : "None configured — prices show NOT AVAILABLE"
                  }
                  tone={s.market_configured ? "ok" : "bad"}
                />
                <Row label="Ledger storage" value={s.storage_status === "ok" ? "Healthy" : s.storage_status} tone={s.storage_status === "ok" ? "ok" : "bad"} />
                <Row label="Audit chain" value={s.audit_chain_intact ? "Intact" : `Broken${s.audit_chain_detail ? `: ${s.audit_chain_detail}` : ""}`} tone={s.audit_chain_intact ? "ok" : "bad"} />
                <Row label="Real-money trading" value="Unavailable — paper trading only" tone="ok" />
                <Row label="Orders on last-known prices" value="Always refused" />
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

        <AgentSwitchesCard />

        <section className="panel analysis-panel" aria-labelledby="sources-title" data-testid="market-sources">
          <div className="panel-heading">
            <div>
              <span className="section-kicker">REAL MARKET DATA</span>
              <h2 id="sources-title">Market data sources</h2>
            </div>
            <div className="button-row">
              <button type="button" className="secondary-button" onClick={() => providers.reload()}>
                Refresh
              </button>
              <button
                type="button"
                className="secondary-button"
                disabled={check.running}
                onClick={() => void check.run().then(() => providers.reload())}
              >
                {check.running ? "Checking…" : "Check providers"}
              </button>
            </div>
          </div>
          <p className="muted">
            SLAIFI asks these sources in order and uses the first that answers. If none can be reached it shows the last real
            price it saved (labelled with when it was observed); if there is none it says NOT AVAILABLE. Nothing is ever invented.
            Each source needs its own free key. Paste it into the box in the table below and it is used straight away, no restart: it is saved on this computer in SLAIFI's
            data folder and is never shown again. A key saved here is used instead of one in the .env file; removing it brings the .env key back. Keys can still be set in .env
            (applications\slaifi\.env) or in the environment.
          </p>
          {providers.loading && !providers.data ? <Loading /> : null}
          {providers.error ? <Notice tone="error" onRetry={providers.reload}>{providers.error}</Notice> : null}
          {providers.data && !providers.data.configured ? (
            <Notice tone="warning" title="No market-data key is set">
              Paste at least one key below (three or more are recommended for failover). Each source offers a free key on its own sign-up page.
            </Notice>
          ) : null}
          {providers.data ? (
            <div className="table-scroll">
              <table className="table" aria-label="Market data sources">
                <thead>
                  <tr>
                    <th>Source</th>
                    <th>Status</th>
                    <th>Provides</th>
                    <th>Calls (min / today)</th>
                    <th>Last success</th>
                    <th>Last problem</th>
                    <th>API key</th>
                  </tr>
                </thead>
                <tbody>
                  {providers.data.providers.map((p) => {
                    const st = providerState(p);
                    const verdict = check.result?.checks.find((c) => c.name === p.name);
                    return (
                      <tr key={p.name} data-testid={`provider-${p.name}`}>
                        <td>
                          <strong>{p.label}</strong>
                          {p.free_tier_note ? <small className="block">{p.free_tier_note}</small> : null}
                        </td>
                        <td className={st.tone === "ok" ? "positive-text" : st.tone === "bad" ? "negative-text" : undefined}>
                          {st.text}
                          {verdict ? (
                            <small className="block" data-testid={`check-${p.name}`}>
                              {verdict.ok ? "✓" : "✗"} {verdict.detail}
                            </small>
                          ) : null}
                        </td>
                        <td>{p.capabilities.length ? p.capabilities.join(", ") : "—"}{p.intervals.length ? ` (${p.intervals.join(", ")})` : ""}</td>
                        <td>{p.configured ? `${p.calls_last_minute} / ${p.calls_today}` : "—"}</td>
                        <td>{p.last_success_at ? dateTime(p.last_success_at) : "—"}</td>
                        <td>{p.last_error ? `${p.last_error}${p.last_error_at ? ` (${dateTime(p.last_error_at)})` : ""}` : "—"}</td>
                        <td>
                          {keyFor(p.name) ? (
                            <ProviderKeyEditor info={keyFor(p.name)!} onChanged={keyChanged} />
                          ) : (
                            <span className="muted">{keys.error ? "Keys can't be changed here right now." : "…"}</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : null}
          {keys.error ? <Notice tone="error" onRetry={keys.reload}>{keys.error}</Notice> : null}
          {check.error ? <Notice tone="error">{check.error}</Notice> : null}
        </section>

        <PlatformFeesCard />

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
