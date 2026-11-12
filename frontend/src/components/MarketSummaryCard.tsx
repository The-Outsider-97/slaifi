import {
  Sparkline,
} from "./Sparkline";

export type SummaryMarket = {
  key: string;
  name: string;
  /** null when no live or saved price exists: the card then says NOT AVAILABLE. */
  value: number | null;
  changePercent: number | null;
  sparkline: readonly number[];
  source: string | null;
  observedAt: string | null;
  lastKnown: boolean;
};

type MarketSummaryCardProps = {
  market: SummaryMarket;
};

export function MarketSummaryCard({
  market,
}: MarketSummaryCardProps) {
  const direction =
    market.changePercent === null
      ? "neutral"
      : market.changePercent > 0
        ? "positive"
        : market.changePercent < 0
          ? "negative"
          : "neutral";

  if (market.value === null) {
    return (
      <article
        className="summary-card summary-card--unavailable"
        data-testid="summary-unavailable"
      >
        <span className="summary-card__name">
          {market.name}
        </span>
        <div className="summary-card__value-row">
          <strong className="not-available">
            NOT AVAILABLE
          </strong>
        </div>
        <div className="market-change market-change--neutral">
          <span>
            No live or saved price
          </span>
        </div>
      </article>
    );
  }

  const formatted =
    new Intl.NumberFormat(
      "en-US",
      {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      },
    ).format(market.value);

  return (
    <article
      className={
        "summary-card" +
        (market.lastKnown
          ? " summary-card--last-known"
          : "")
      }
      data-source={market.source ?? undefined}
    >
      <span className="summary-card__name">
        {market.name}
      </span>

      <div className="summary-card__value-row">
        <strong>
          {formatted}
        </strong>

        <Sparkline
          values={market.sparkline}
          direction={direction}
        />
      </div>

      {market.lastKnown ? (
        <small
          className="last-known-note"
          data-testid="last-known-note"
        >
          LAST KNOWN · observed{" "}
          {market.observedAt
            ? new Date(
                market.observedAt,
              ).toLocaleString()
            : "—"}
        </small>
      ) : null}

      <div
        className={
          `market-change ` +
          `market-change--${direction}`
        }
      >
        {market.changePercent !==
        null ? (
          <>
            <strong>
              {market.changePercent >
              0
                ? "+"
                : ""}
              {market.changePercent.toFixed(
                2,
              )}
              %
            </strong>
            <span>today</span>
          </>
        ) : (
          <span>
            Day change unavailable
          </span>
        )}
      </div>
    </article>
  );
}
