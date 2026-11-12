import { age, dateTime } from "../../lib/format";
import type { Provenance } from "../../types/finance";

export type FreshnessKind = "live" | "delayed" | "retrieved" | "last-known" | "unavailable";

export const NOT_AVAILABLE = "NOT AVAILABLE";

/**
 * What kind of data this is, in words a person cannot mistake.
 * Saved (last known) data always shows when it was observed; missing data says NOT AVAILABLE.
 */
export function freshnessLabel(p: Provenance): { kind: FreshnessKind; text: string } {
  if (p.mode === "unavailable" || p.available === false) {
    return { kind: "unavailable", text: NOT_AVAILABLE };
  }
  if (p.last_known || p.mode === "last_known") {
    return {
      kind: "last-known",
      text: `LAST KNOWN DATA · observed ${dateTime(p.observed_at)}`,
    };
  }
  const ageText = age(p.age_seconds);
  if (p.mode === "retrieved") {
    return { kind: "retrieved", text: `RETRIEVED · ${p.source ?? "provider"} · ${ageText}` };
  }
  if (p.mode === "delayed" || p.delayed === true) {
    return { kind: "delayed", text: `DELAYED DATA · ${ageText}` };
  }
  if (p.mode === "live_delay_unknown" || p.delayed === null) {
    return { kind: "delayed", text: `PROVIDER DATA · delay unknown · ${ageText}` };
  }
  return { kind: "live", text: `LIVE · ${ageText}` };
}

/** The tooltip lists exactly which sources were tried and what each one answered. */
function details(p: Provenance): string {
  const lines: (string | null)[] = [
    p.source ? `Source: ${p.source}` : "Source: none",
    p.observed_at ? `Observed: ${dateTime(p.observed_at)}` : null,
    p.saved_at ? `Saved locally: ${dateTime(p.saved_at)}` : null,
    p.retrieved_at ? `Checked: ${dateTime(p.retrieved_at)}` : null,
    ...(p.attempts ?? []).map((a) => `${a.source}: ${a.outcome}${a.detail ? ` (${a.detail})` : ""}`),
    ...p.notes,
  ];
  return lines.filter(Boolean).join("\n");
}

export function FreshnessBadge({ provenance }: { provenance: Provenance | null | undefined }) {
  if (!provenance) return null;
  const { kind, text } = freshnessLabel(provenance);
  const closed = kind !== "unavailable" && provenance.market_open === false ? " · market closed" : "";
  return (
    <span className={`freshness freshness--${kind}`} title={details(provenance)} data-testid="freshness-badge">
      <span className="freshness__dot" aria-hidden="true" />
      {text}
      {closed}
    </span>
  );
}
