// shared/openapi.yaml (v0.2.0) şemalarının elle yazılmış karşılıkları.
// openapi dondurulunca `npx openapi-typescript ../shared/openapi.yaml -o api/schema.d.ts`
// ile üretilen tiplere geçilecek; alan adları birebir aynı tutuldu.

/** index yalnızca XU100 içindir; tahmin/senaryo/sinyal üretilmez (db_schema v0.2) */
export type AssetType = 'stock' | 'fund' | 'index';
export type Direction = 'up' | 'down' | 'flat';
/** Kısa vadeli tahmin ufukları (iş günü). 30/120 yalnızca senaryolarda. */
export type Horizon = 1 | 5 | 20;
export type Risk = 'low' | 'medium' | 'high';
/** Kişi 2'nin karar motoru (app/models/decision.py) */
export type Regime = 'trend' | 'range' | 'high_vol';

export interface AssetListItem {
  code: string;
  name: string;
  type: AssetType;
  /** Hisse: sektör, fon: fon türü */
  sector?: string | null;
  last_price: number;
  change_pct: number;
}

export interface PricePoint {
  date: string; // YYYY-MM-DD
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  adj_close?: number | null;
  volume: number | null;
}

export interface ForecastBand {
  model: string; // 'ensemble' | 'timesfm' | 'chronos' | 'naive' | 'naive_drift' | 'ma' | 'arima'
  horizon: 1 | 5 | 20 | 30 | 120;
  p10: number;
  /** 120 günde null (nokta tahmin yok) */
  p50: number | null;
  p90: number;
}

/** p50 yoksa bandın ortası */
export const mid = (b: Pick<ForecastBand, 'p10' | 'p50' | 'p90'>) => b.p50 ?? (b.p10 + b.p90) / 2;

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

export interface Indicators {
  rsi?: number;
  macd_hist?: number;
  ma20_above_ma50?: boolean;
  atr_pct?: number;
  [k: string]: unknown;
}

export interface Analysis {
  code: string;
  run_date: string;
  horizon: Horizon;
  range: { low: number; mid: number; high: number };
  direction: Direction;
  confidence: number;
  risk: Risk;
  regime?: Regime | null;
  weights?: Record<string, number> | null;
  indicators?: Indicators | null;
  /** Gece uzman yorumu (ai_explanations.text); yoksa null */
  comment: string | null;
}

export interface Signal {
  id: number;
  code: string;
  side: 'buy' | 'sell';
  horizon: 1 | 5 | 20 | 30;
  confidence: number;
  suggested_qty: number | null;
  stop_level: number | null;
  created_at: string;
  /** Ufuk dolunca doldurulur */
  outcome: { realized: number; hit: boolean } | null;
}

export interface ScreenerFilter {
  type?: AssetType;
  direction?: Direction;
  min_conf?: number;
}

export type RiskProfile = 'cautious' | 'balanced' | 'aggressive';

export interface QuietHours {
  start: string; // "22:30"
  end: string; // "08:00"
}

export interface ProfileOut {
  email: string;
  risk_profile: RiskProfile;
  /** TL; null = girilmemiş */
  budget: number | null;
  quiet_hours: QuietHours | null;
  daily_push_limit: number | null;
}

/** Yalnızca gönderilen alanlar güncellenir; silmek için null */
export type ProfileUpdate = Partial<{ [K in keyof Omit<ProfileOut, 'email'>]: ProfileOut[K] | null }>;

export interface PositionCreate {
  code: string;
  qty: number;
  buy_price: number;
  buy_date: string;
  signal_id?: number | null;
}

export interface Position extends PositionCreate {
  id: number;
  sell_price: number | null;
  sell_date: string | null;
}
