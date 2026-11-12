import type { Explanation } from "../../types/finance";
import { humanize } from "../../lib/format";

/** SLAI's interpretation, labelled as such. It never carries a number the engines did not produce. */
export function Explained({ explanation }: { explanation: Explanation }) {
  if (!explanation) return null;
  if (explanation.status !== "available" || !explanation.text) {
    return (
      <div className="explained explained--off" role="status">
        <strong>SLAI interpretation</strong>
        <span>
          {explanation.warnings[0] ?? "SLAI interpretation is not available right now. The deterministic result above is unaffected."}
        </span>
      </div>
    );
  }
  return (
    <div className="explained">
      <strong>SLAI interpretation{explanation.agent ? ` · ${explanation.agent}` : ""}</strong>
      <p>{explanation.text}</p>
      <small>{explanation.label}</small>
      {explanation.validation_status ? <small>Quality check: {humanize(explanation.validation_status)}</small> : null}
      {explanation.warnings.map((warning) => (
        <small key={warning}>{warning}</small>
      ))}
    </div>
  );
}
