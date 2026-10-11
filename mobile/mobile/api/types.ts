// shared/openapi.yaml'daki şemaların elle yazılmış karşılıkları.
// openapi dondurulunca `npx openapi-typescript ../shared/openapi.yaml -o api/schema.d.ts`
// ile üretilen tiplere geçilecek; alan adları birebir aynı tutuldu.

export type AssetType = 'stock' | 'fund';
export type Direction = 'up' | 'down' | 'flat';
export type Horizon = 1 | 5 | 20;
export type Risk = 'low' | 'medium' | 'high';

export interface AssetListItem {
  code: string;
  name: string;
  type: AssetType;
  last_price: number;
  change_pct: number;
}

export interface PricePoint {
  date: string; // YYYY-MM-DD
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  volume: number | null;
}

export interface ForecastBand {
  model: string; // 'ensemble' | 'timesfm' | 'chronos' ...
  horizon: number;
  p10: number;
  p50: number;
  p90: number;
}

export interface Scenario {
  horizon: 30 | 120;
  bear: number;
  base: number;
  bull: number;
}

export interface Forecast {
  code: string;
  run_date: string;
  bands: ForecastBand[];
  scenarios: Scenario[];
}

export interface Analysis {
  code: string;
  run_date: string;
  horizon: Horizon;
  range: { low: number; mid: number; high: number };
  direction: Direction;
  confidence: number;
  risk: Risk;
  regime: string;
  weights: Record<string, number>;
  indicators: { rsi?: number; macd_hist?: number; ma20_above_ma50?: boolean; atr_pct?: number; [k: string]: unknown };
  comment: string | null;
}

export interface Signal {
  id: string;
  code: string;
  side: 'buy' | 'sell';
  horizon: Horizon;
  confidence: number;
  suggested_qty: number | null;
  stop_level: number | null;
  created_at: string;
  outcome: string | null;
}

export interface ScreenerFilter {
  type?: AssetType;
  direction?: Direction;
  min_conf?: number;
}
