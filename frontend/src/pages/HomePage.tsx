import { useEffect, useState } from "react";

import { fetchMarketOverview } from "../services/api";
import type { MarketOverview } from "../types/market";

export function HomePage() {
  const [overview, setOverview] = useState<MarketOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    fetchMarketOverview(controller.signal)
      .then((data) => {
        setOverview(data);
        setError(null);
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "Unable to load market overview");
      });

    return () => controller.abort();
  }, []);

  return (
    <main className="page">
      <section className="hero">
        <div>
          <p className="eyebrow"><span>●</span> Architecture foundation</p>
          <h1>Financial intelligence built around evidence, risk and goals.</h1>
          <p className="hero-copy">
            This first vertical slice proves provider normalization, application orchestration,
            API delivery and the SLAIFI interface. Predictive recommendations are intentionally not active yet.
          </p>
        </div>
        <div className="status-card">
          <span className="status-label">DATA MODE</span>
          <strong>{overview?.data_mode.toUpperCase() ?? "CONNECTING"}</strong>
          <span className="status-note">No live trading or prediction logic enabled</span>
        </div>
      </section>

      <section aria-labelledby="market-overview-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow"><span>●</span> Market</p>
            <h2 id="market-overview-title">Overview</h2>
          </div>
          {overview ? <time>{new Date(overview.generated_at).toLocaleTimeString()}</time> : null}
        </div>

        {error ? <div className="error-card" role="alert">{error}</div> : null}

        <div className="quote-grid" aria-live="polite">
          {overview?.quotes.map((quote) => {
            const change = quote.change_percent === null ? null : Number(quote.change_percent);
            const direction = change === null ? "neutral" : change > 0 ? "positive" : change < 0 ? "negative" : "neutral";
            return (
              <article className="quote-card" key={quote.symbol}>
                <div className="quote-card__top">
                  <div>
                    <strong>{quote.symbol}</strong>
                    <span>{quote.asset_class}</span>
                  </div>
                  <span className="source-badge">{quote.source}</span>
                </div>
                <div className="quote-price">
                  {new Intl.NumberFormat(undefined, {
                    style: "currency",
                    currency: quote.currency,
                    maximumFractionDigits: 2,
                  }).format(Number(quote.price))}
                </div>
                <div className={`quote-change quote-change--${direction}`}>
                  {change === null ? "—" : `${change > 0 ? "+" : ""}${change.toFixed(2)}%`}
                </div>
              </article>
            );
          })}
          {!overview && !error ? <div className="loading-card">Loading normalized market data…</div> : null}
        </div>
      </section>
    </main>
  );
}
