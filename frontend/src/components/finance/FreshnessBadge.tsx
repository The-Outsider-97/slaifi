import { age, dateTime } from "../../lib/format";
import type { Provenance } from "../../types/finance";

/** What kind of data this is, in words a person cannot mistake: mock is never shown as live. */
export function freshnessLabel(p: Provenance): { kind: "mock" | "live" | "delayed" | "stale"; text: string } {
  if (p.illustrative || p.mode === "mock") {
    return { kind: "mock", text: "ILLUSTRATIVE DATA · not real market prices" };
  }
  const ageText = age(p.age_seconds);
  if (p.mode === "delayed" || p.delayed === true) {
    return { kind: "delayed", text: `DELAYED DATA · ${ageText}` };
  }
  if (p.mode === "live_delay_unknown" || p.delayed === null) {
    return { kind: "delayed", text: `PROVIDER DATA · delay unknown · ${ageText}` };
  }
  return { kind: "live", text: `LIVE · ${ageText}` };
}

export function FreshnessBadge({ provenance }: { provenance: Provenance | null | undefined }) {
  if (!provenance) return null;
  const { kind, text } = freshnessLabel(provenance);
  const closed = provenance.market_open === false ? " · market closed" : "";
  const title = [
    `Source: ${provenance.source}`,
    provenance.observed_at ? `Observed: ${dateTime(provenance.observed_at)}` : null,
    provenance.retrieved_at ? `Retrieved: ${dateTime(provenance.retrieved_at)}` : null,
    ...provenance.notes,
  ]
    .filter(Boolean)
    .join("\n");
  return (
    <span className={`freshness freshness--${kind}`} title={title} data-testid="freshness-badge">
      <span className="freshness__dot" aria-hidden="true" />
      {text}
      {closed}
    </span>
  );
}
