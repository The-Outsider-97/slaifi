/**
 * Price-history requests shared by everything on a page.
 *
 * Two charts (or a chart and a comparison) asking for the same symbol and range make one request,
 * and switching back to a range seen a moment ago is instant. Only real, non-empty answers are
 * kept, and only for a short time, so a failed or empty answer is always retried. The server
 * keeps its own cache; this one just avoids asking twice.
 */

import { fetchSeries } from "../services/finance";
import type { SeriesResponse } from "../types/finance";

const TTL_MS = 5 * 60_000;
const MAX_ENTRIES = 40;

type Entry = { at: number; value: SeriesResponse };
const stored = new Map<string, Entry>();
const inflight = new Map<string, Promise<SeriesResponse>>();

const keyOf = (symbol: string, days: number, overlays: readonly string[]) =>
  `${symbol.toUpperCase()}|${days}|${[...overlays].sort().join(",")}`;

export function loadSeries(
  symbol: string,
  days: number,
  overlays: readonly string[] = [],
  now: () => number = Date.now,
): Promise<SeriesResponse> {
  const key = keyOf(symbol, days, overlays);
  const hit = stored.get(key);
  if (hit && now() - hit.at < TTL_MS) return Promise.resolve(hit.value);
  const pending = inflight.get(key);
  if (pending) return pending;

  const request = fetchSeries(symbol, { interval: "1day", days, overlays: [...overlays] })
    .then((value) => {
      if (value.bars.length > 0 && value.provenance.mode !== "unavailable") {
        stored.set(key, { at: now(), value });
        while (stored.size > MAX_ENTRIES) {
          const oldest = stored.keys().next().value;
          if (oldest === undefined) break;
          stored.delete(oldest);
        }
      }
      return value;
    })
    .finally(() => {
      inflight.delete(key);
    });
  inflight.set(key, request);
  return request;
}

export function clearSeriesCache(): void {
  stored.clear();
  inflight.clear();
}
