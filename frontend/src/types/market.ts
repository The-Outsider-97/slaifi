export type MarketQuote = {
  symbol: string;
  asset_class: string;
  price: string;
  currency: string;
  change_percent: string | null;
  observed_at: string;
  source: string;
};

export type MarketOverview = {
  generated_at: string;
  quotes: MarketQuote[];
  data_mode: string;
};
