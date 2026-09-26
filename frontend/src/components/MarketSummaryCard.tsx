import { Sparkline } from "./Sparkline";

export type SummaryMarket = {
  key: string;
  name: string;
  value: number;
  changePercent: number;
  sparkline: readonly number[];
  source: "api" | "illustrative";
};

type MarketSummaryCardProps = {
  market: SummaryMarket;
};

export function MarketSummaryCard({ market }: MarketSummaryCardProps) {
  const direction = market.changePercent > 0 ? "positive" : market.changePercent < 0 ? "negative" : "neutral";
  const formatted = new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(market.value);

  return (
    <article className="summary-card" data-source={market.source}>
      <span className="summary-card__name">{market.name}</span>
      <div className="summary-card__value-row">
        <strong>{formatted}</strong>
        <Sparkline values={market.sparkline} direction={direction} />
      </div>
      <div className={`market-change market-change--${direction}`}>
        <strong>{market.changePercent > 0 ? "+" : ""}{market.changePercent.toFixed(2)}%</strong>
        <span>today</span>
      </div>
    </article>
  );
}
