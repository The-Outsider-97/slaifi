import type { MarketOverview } from "../types/market";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function fetchMarketOverview(signal?: AbortSignal): Promise<MarketOverview> {
  const response = await fetch(`${API_BASE_URL}/api/v1/market/overview`, {
    headers: { Accept: "application/json" },
    signal,
  });

  if (!response.ok) {
    throw new Error(`Market overview request failed with status ${response.status}`);
  }

  return (await response.json()) as MarketOverview;
}
