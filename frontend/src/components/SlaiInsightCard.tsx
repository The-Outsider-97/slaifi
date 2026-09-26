import type { MarketAnalysisResponse, SlaiRuntimeStatus } from "../types/market";

type SlaiInsightCardProps = {
  runtime: SlaiRuntimeStatus | null;
  analysis: MarketAnalysisResponse | null;
  loading: boolean;
  error: string | null;
  onExplore: () => void;
};

function runtimeLabel(runtime: SlaiRuntimeStatus | null, statusOverride?: string) {
  if (!runtime) return "SLAI runtime status unavailable";
  const agent = runtime.agent ? runtime.agent.replace(/_/g, " ") : "Reasoning Agent";
  const version = runtime.agent_version ? ` v${runtime.agent_version}` : "";
  return `SLAI analysis · illustrative data · ${agent}${version} · ${statusOverride ?? runtime.status}`;
}

export function SlaiInsightCard({ runtime, analysis, loading, error, onExplore }: SlaiInsightCardProps) {
  const reasoning = analysis?.reasoning ?? null;
  const connected = runtime?.status === "available" || runtime?.status === "degraded";
  const interpretation = reasoning?.interpretation?.trim();

  return (
    <aside className="panel insight-panel" aria-labelledby="slai-insight-title">
      <div className="insight-header">
        <span className="insight-label">✧ SLAI INSIGHT</span>
        <span>01 / 03</span>
      </div>
      <span className="insight-spark" aria-hidden="true">✧</span>
      <span className="section-kicker">THE BIG PICTURE</span>
      <h2 id="slai-insight-title">
        {interpretation ? "Evidence, in context." : <>Stay invested.<br />Stay selective.</>}
      </h2>
      <p className={interpretation ? "insight-copy insight-copy--live" : "insight-copy"}>
        {interpretation ?? "This illustrative scenario favors a measured approach: maintain diversification and avoid chasing recent momentum."}
      </p>

      <div className="insight-meta">
        {reasoning ? (
          <>
            <div><span>Reasoning type</span><strong>{reasoning.reasoning_strategy ?? "Contextual"}</strong></div>
            <div><span>Runtime state</span><strong>{reasoning.status}</strong></div>
          </>
        ) : (
          <>
            <div><span>Example stance</span><strong>Balanced</strong></div>
            <div><span>Risk level</span><strong>Moderate</strong></div>
          </>
        )}
      </div>

      {error ? <p className="insight-error" role="alert">{error}</p> : null}
      <button
        className="primary-cta"
        type="button"
        disabled={!connected || loading}
        onClick={onExplore}
      >
        <span>{loading ? "Reasoning…" : reasoning ? "Refresh the reasoning" : "Explore the reasoning"}</span>
        <span aria-hidden="true">↗</span>
      </button>
      <div className={`runtime-provenance runtime-provenance--${reasoning?.status ?? runtime?.status ?? "unknown"}`}>
        {reasoning
          ? runtimeLabel(runtime, reasoning.status)
          : connected
            ? runtimeLabel(runtime)
            : `Illustrative analysis · SLAI engine ${runtime?.status ?? "not connected"}`}
      </div>
    </aside>
  );
}
