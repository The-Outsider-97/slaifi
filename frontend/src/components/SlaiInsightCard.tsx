import type {
  MarketAnalysisResponse,
  SlaiRuntimeStatus,
} from "../types/market";

type Props = {
  runtime: SlaiRuntimeStatus | null;
  analysis: MarketAnalysisResponse | null;
  loading: boolean;
  error: string | null;
  hasEvidence: boolean;
  onExplore: () => void;
};

export function SlaiInsightCard({
  runtime,
  analysis,
  loading,
  error,
  hasEvidence,
  onExplore,
}: Props) {
  const reasoning =
    analysis?.reasoning ?? null;

  const connected =
    runtime?.status === "available" ||
    runtime?.status === "degraded";

  const interpretation =
    reasoning?.interpretation?.trim() ??
    null;

  const agent =
    reasoning?.agent ??
    runtime?.agent ??
    null;

  const confidence =
    reasoning?.confidence ??
    null;

  return (
    <aside
      className="panel insight-panel"
      aria-labelledby="slai-insight-title"
    >
      <div className="insight-header">
        <span className="insight-label">
          ✧ SLAI INSIGHT
        </span>

        <span>
          {reasoning
            ? reasoning.status
            : runtime?.status ??
              "unavailable"}
        </span>
      </div>

      <span
        className="insight-spark"
        aria-hidden="true"
      >
        ✧
      </span>

      <span className="section-kicker">
        THE BIG PICTURE
      </span>

      <h2 id="slai-insight-title">
        {interpretation
          ? "Evidence, in context."
          : connected
            ? "Ready to analyse."
            : "SLAI unavailable."}
      </h2>

      <p
        className={
          interpretation
            ? "insight-copy insight-copy--live"
            : "insight-copy"
        }
      >
        {interpretation ??
          (connected
            ? hasEvidence
              ? "Run SLAI reasoning against the current market series."
              : "Real historical market evidence is required before analysis can run."
            : "Core market data remains available without SLAI interpretation.")}
      </p>

      <div className="insight-meta">
        <div>
          <span>Runtime</span>
          <strong>
            {reasoning?.status ??
              runtime?.status ??
              "Unavailable"}
          </strong>
        </div>

        <div>
          <span>Confidence</span>
          <strong>
            {confidence === null
              ? "Not reported"
              : `${(
                  confidence *
                  100
                ).toFixed(0)}%`}
          </strong>
        </div>

        {reasoning?.validation_status ? (
          <div>
            <span>
              Quality
            </span>
            <strong>
              {
                reasoning.validation_status
              }
            </strong>
          </div>
        ) : null}

        {reasoning?.safety_status ? (
          <div>
            <span>
              Safety
            </span>
            <strong>
              {
                reasoning.safety_status
              }
            </strong>
          </div>
        ) : null}

        {reasoning?.reasoning_strategy ? (
          <div>
            <span>
              Strategy
            </span>
            <strong>
              {
                reasoning.reasoning_strategy
              }
            </strong>
          </div>
        ) : null}

        {agent ? (
          <div>
            <span>Agent</span>
            <strong>
              {agent.replace(
                /_/g,
                " ",
              )}
            </strong>
          </div>
        ) : null}
      </div>

      {reasoning?.warnings?.length ? (
        <p
          className="insight-warning"
          role="status"
        >
          {reasoning.warnings.join(" ")}
        </p>
      ) : null}

      {error ? (
        <p
          className="insight-error"
          role="alert"
        >
          {error}
        </p>
      ) : null}

      <button
        className="primary-cta"
        type="button"
        disabled={
          !connected ||
          !hasEvidence ||
          loading
        }
        onClick={onExplore}
      >
        <span>
          {loading
            ? "Reasoning…"
            : reasoning
              ? "Refresh reasoning"
              : "Explore the reasoning"}
        </span>

        <span aria-hidden="true">
          ↗
        </span>
      </button>

      <div
        className={
          `runtime-provenance ` +
          `runtime-provenance--${
            reasoning?.status ??
            runtime?.status ??
            "unknown"
          }`
        }
      >
        {reasoning
          ? `SLAI analysis · ${
              agent ??
              "reasoning agent"
            }`
          : connected
            ? "SLAI connected · no analysis generated yet"
            : "SLAI reasoning currently unavailable"}
      </div>
    </aside>
  );
}