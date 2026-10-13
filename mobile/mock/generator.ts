// Sahte veri üreticisi.
// • Deterministik: aynı kod her açılışta aynı grafiği verir (koddan türetilen tohum).
// • Gerçekçi: fiyatlar rastgele yürüyüşle (geometrik Brownian hareketi) üretilir; hafta sonları atlanır;
//   hisselerde OHLC + hacim, fonlarda yalnızca kapanış (TEFAS'taki gibi).
// • Tutarlı: tahmin bandı, senaryolar, analiz ve sinyal aynı fiyat serisinden hesaplanır.
// Şekiller api/types.ts (= shared/openapi.yaml) ile birebir aynıdır.
import type {
  Analysis,
  AssetListItem,
  AssetType,
  Direction,
  Forecast,
  Horizon,
  PricePoint,
  Risk,
  Regime,
  Signal,
} from '@/api/types';
import { mid } from '@/api/types';

interface Meta {
  code: string;
  name: string;
  type: AssetType;
  start: number; // ~5 yıl önceki fiyat
  drift: number; // yıllık eğilim
  vol: number; // yıllık oynaklık
  sector?: string;
}

export const ASSETS: Meta[] = [
  { code: 'THYAO', name: 'Türk Hava Yolları', type: 'stock', sector: 'Ulaştırma', start: 18, drift: 0.55, vol: 0.42 },
  { code: 'ASELS', name: 'Aselsan', type: 'stock', sector: 'Savunma', start: 22, drift: 0.38, vol: 0.4 },
  { code: 'BIMAS', name: 'BİM Birleşik Mağazalar', type: 'stock', sector: 'Perakende', start: 75, drift: 0.36, vol: 0.32 },
  { code: 'KCHOL', name: 'Koç Holding', type: 'stock', sector: 'Holding', start: 24, drift: 0.4, vol: 0.36 },
  { code: 'TUPRS', name: 'Tüpraş', type: 'stock', sector: 'Enerji', start: 20, drift: 0.42, vol: 0.38 },
  { code: 'EREGL', name: 'Ereğli Demir Çelik', type: 'stock', sector: 'Metal', start: 12, drift: 0.22, vol: 0.37 },
  { code: 'SISE', name: 'Şişecam', type: 'stock', sector: 'Cam', start: 9, drift: 0.3, vol: 0.4 },
  { code: 'AKBNK', name: 'Akbank', type: 'stock', sector: 'Bankacılık', start: 7, drift: 0.48, vol: 0.45 },
  { code: 'GARAN', name: 'Garanti BBVA', type: 'stock', sector: 'Bankacılık', start: 10, drift: 0.5, vol: 0.44 },
  { code: 'FROTO', name: 'Ford Otosan', type: 'stock', sector: 'Otomotiv', start: 140, drift: 0.34, vol: 0.35 },
  { code: 'IPB', name: 'İş Portföy BIST Banka Endeksi Fonu', type: 'fund', sector: 'Hisse senedi', start: 0.9, drift: 0.38, vol: 0.3 },
  { code: 'TTE', name: 'İş Portföy BIST Teknoloji Ağırlıklı Fon', type: 'fund', sector: 'Hisse senedi', start: 2.1, drift: 0.4, vol: 0.26 },
  { code: 'AFT', name: 'Ak Portföy Yeni Teknolojiler Fonu', type: 'fund', sector: 'Değişken', start: 0.7, drift: 0.36, vol: 0.24 },
  { code: 'MAC', name: 'Marmara Capital Hisse Fonu', type: 'fund', sector: 'Hisse senedi', start: 4.0, drift: 0.38, vol: 0.27 },
  { code: 'YAY', name: 'Yapı Kredi Yabancı Teknoloji Fonu', type: 'fund', sector: 'Yabancı hisse', start: 1.4, drift: 0.32, vol: 0.22 },
  { code: 'GSP', name: 'Garanti Portföy Para Piyasası Fonu', type: 'fund', sector: 'Para piyasası', start: 1.0, drift: 0.42, vol: 0.02 },
];

export const BIST100_META: Meta = { code: 'XU100', name: 'BIST 100', type: 'index', start: 1400, drift: 0.42, vol: 0.28 };

const TRADING_DAYS = 252;
const HISTORY_DAYS = TRADING_DAYS * 5;

// ---- Rastgelelik --------------------------------------------------------------------------------

function seedFrom(s: string) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return h >>> 0;
}

function rng(seed: number) {
  let a = seed || 1;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Standart normal (Box–Muller) */
function gauss(r: () => number) {
  const u = Math.max(r(), 1e-9);
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * r());
}

const round = (v: number, type: AssetType) => (type === 'fund' ? Math.round(v * 10000) / 10000 : Math.round(v * 100) / 100);

// ---- İş günleri -----------------------------------------------------------------------------------

function tradingDates(count: number): string[] {
  const out: string[] = [];
  const d = new Date();
  d.setHours(12, 0, 0, 0);
  // bugün hafta sonuysa son cumaya git
  while (d.getDay() === 0 || d.getDay() === 6) d.setDate(d.getDate() - 1);
  while (out.length < count) {
    if (d.getDay() !== 0 && d.getDay() !== 6) out.push(d.toISOString().slice(0, 10));
    d.setDate(d.getDate() - 1);
  }
  return out.reverse();
}

function addTradingDays(from: string, n: number): string {
  const d = new Date(`${from}T12:00:00`);
  let left = n;
  while (left > 0) {
    d.setDate(d.getDate() + 1);
    if (d.getDay() !== 0 && d.getDay() !== 6) left--;
  }
  return d.toISOString().slice(0, 10);
}
export { addTradingDays };

// ---- Fiyat serisi -----------------------------------------------------------------------------------

const cache = new Map<string, PricePoint[]>();

function metaOf(code: string): Meta {
  if (code === BIST100_META.code) return BIST100_META;
  return (
    ASSETS.find((a) => a.code === code) ?? {
      code,
      name: code,
      type: 'stock',
      start: 10 + (seedFrom(code) % 90),
      drift: 0.3,
      vol: 0.38,
    }
  );
}

export function genHistory(code: string): PricePoint[] {
  const hit = cache.get(code);
  if (hit) return hit;

  const m = metaOf(code);
  const r = rng(seedFrom(code));
  const dates = tradingDates(HISTORY_DAYS);
  const dt = 1 / TRADING_DAYS;
  const out: PricePoint[] = [];

  let price = m.start;
  let vol = m.vol;
  for (const date of dates) {
    // oynaklık kümelenmesi: sakin ve hareketli dönemler
    vol = Math.max(m.vol * 0.5, Math.min(m.vol * 1.8, vol + (m.vol - vol) * 0.05 + gauss(r) * m.vol * 0.06));
    const ret = (m.drift - (vol * vol) / 2) * dt + vol * Math.sqrt(dt) * gauss(r);
    const open = price;
    const close = price * Math.exp(ret);
    const span = Math.abs(close - open) + price * vol * Math.sqrt(dt) * (0.4 + r() * 0.8);
    const high = Math.max(open, close) + span * r() * 0.6;
    const low = Math.min(open, close) - span * r() * 0.6;
    price = close;

    out.push(
      m.type === 'fund'
        ? { date, open: null, high: null, low: null, close: round(close, 'fund'), volume: null }
        : {
            date,
            open: round(open, 'stock'),
            high: round(high, 'stock'),
            low: round(Math.max(low, 0.01), 'stock'),
            close: round(close, 'stock'),
            volume: Math.round((5 + r() * 20) * 1e6 * (1 + Math.abs(ret) * 30)),
          },
    );
  }
  cache.set(code, out);
  return out;
}

// ---- Liste ---------------------------------------------------------------------------------------------

function listItem(m: Meta): AssetListItem {
  const h = genHistory(m.code);
  const last = h[h.length - 1].close;
  const prev = h[h.length - 2].close;
  return { code: m.code, name: m.name, type: m.type, sector: m.sector ?? null, last_price: last, change_pct: Math.round(((last - prev) / prev) * 10000) / 100 };
}

export function genAssets(type?: AssetType, q?: string): AssetListItem[] {
  const norm = (s: string) => s.toLocaleLowerCase('tr-TR');
  return ASSETS.filter((a) => !type || a.type === type)
    .filter((a) => !q || norm(a.code).includes(norm(q)) || norm(a.name).includes(norm(q)))
    .map(listItem);
}

export function genAsset(code: string): AssetListItem {
  return listItem(metaOf(code));
}

export function genIndex() {
  const h = genHistory(BIST100_META.code);
  return { ...listItem(BIST100_META), series: h.slice(-30).map((p) => p.close) };
}

// ---- Göstergeler -------------------------------------------------------------------------------------

function sma(v: number[], n: number) {
  const s = v.slice(-n);
  return s.reduce((a, b) => a + b, 0) / s.length;
}

function ema(v: number[], n: number) {
  const k = 2 / (n + 1);
  return v.reduce((prev, x, i) => (i === 0 ? x : x * k + prev * (1 - k)));
}

function rsi(v: number[], n = 14) {
  let gain = 0;
  let loss = 0;
  for (let i = v.length - n; i < v.length; i++) {
    const d = v[i] - v[i - 1];
    if (d > 0) gain += d;
    else loss -= d;
  }
  if (loss === 0) return 100;
  return 100 - 100 / (1 + gain / loss);
}

function dailyVol(v: number[], n = 20) {
  const r = v.slice(-n - 1).map((x, i, a) => (i === 0 ? 0 : Math.log(x / a[i - 1]))).slice(1);
  const mean = r.reduce((a, b) => a + b, 0) / r.length;
  return Math.sqrt(r.reduce((a, b) => a + (b - mean) ** 2, 0) / r.length);
}

// ---- Tahmin ve senaryolar -------------------------------------------------------------------------------

const Z90 = 1.2816; // p10/p90 için z

export function genForecast(code: string): Forecast {
  const h = genHistory(code);
  const closes = h.map((p) => p.close);
  const last = closes[closes.length - 1];
  const type = metaOf(code).type;
  const sigma = dailyVol(closes);
  const r = rng(seedFrom(`${code}-fc`));
  // modelin "görüşü": son 60 günlük eğilim + biraz gürültü, abartısız
  const mu = Math.log(last / closes[closes.length - 60]) / 60 * 0.4 + (r() - 0.5) * 0.002;

  const band = (horizon: Horizon, model = 'ensemble', bias = 0) => {
    const m = (mu + bias) * horizon;
    const s = sigma * Math.sqrt(horizon);
    return {
      model,
      horizon,
      p10: round(last * Math.exp(m - Z90 * s), type),
      p50: round(last * Math.exp(m), type),
      p90: round(last * Math.exp(m + Z90 * s), type),
    };
  };

  const bands = ([1, 5, 20] as const).flatMap((hz) => [
    band(hz),
    band(hz, 'timesfm', 0.0004),
    band(hz, 'chronos', -0.0003),
  ]);

  const scen = (horizon: 30 | 120) => {
    const s = sigma * Math.sqrt(horizon);
    const m = mu * horizon;
    return {
      horizon,
      bear: round(last * Math.exp(m - 1.4 * s), type),
      base: round(last * Math.exp(m), type),
      bull: round(last * Math.exp(m + 1.4 * s), type),
    };
  };

  return { code, run_date: h[h.length - 1].date, bands, scenarios: [scen(30), scen(120)] };
}

/** Senaryo grafiği için günlük yol: bugünden ufka doğru yumuşak eğri */
export function scenarioPath(last: number, target: number, days: number) {
  return Array.from({ length: days + 1 }, (_, i) => {
    const t = i / days;
    const eased = t * t * (3 - 2 * t); // smoothstep
    return last + (target - last) * eased;
  });
}

// ---- Analiz --------------------------------------------------------------------------------------------

export function genAnalysis(code: string, horizon: Horizon): Analysis {
  const h = genHistory(code);
  const closes = h.map((p) => p.close);
  const last = closes[closes.length - 1];
  const fc = genForecast(code).bands.find((b) => b.model === 'ensemble' && b.horizon === horizon)!;
  const r = rng(seedFrom(`${code}-${horizon}-an`));

  const change = (mid(fc) - last) / last;
  const width = (fc.p90 - fc.p10) / last;
  const direction: Direction = Math.abs(change) < width * 0.08 ? 'flat' : change > 0 ? 'up' : 'down';
  const rsiV = rsi(closes);
  const macd = ema(closes.slice(-60), 12) - ema(closes.slice(-60), 26);
  const ma20 = sma(closes, 20);
  const ma50 = sma(closes, 50);
  const atrPct = dailyVol(closes) * 100 * 1.25;
  const risk: Risk = atrPct < 1.6 ? 'low' : atrPct < 2.8 ? 'medium' : 'high';
  const agree = (direction === 'up') === ma20 > ma50 ? 12 : -6;
  const confidence = Math.round(Math.max(45, Math.min(88, 58 + agree + (r() - 0.5) * 20 - (risk === 'high' ? 6 : 0))));
  const regime: Regime = Math.abs(ma20 - ma50) / last > 0.03 ? 'trend' : atrPct > 2.8 ? 'high_vol' : 'range';
  const wT = Math.round((0.45 + r() * 0.2) * 100) / 100;

  const dirText = direction === 'up' ? 'hafif yükseliş' : direction === 'down' ? 'hafif düşüş' : 'yatay seyir';
  const comment =
    `Modeller ${horizon} günlük ufukta ${dirText} yönünde ${confidence >= 65 ? 'büyük ölçüde uzlaşıyor' : 'kısmen ayrışıyor'}. ` +
    `RSI ${rsiV.toFixed(0)} ile ${rsiV > 70 ? 'aşırı alım bölgesine yakın' : rsiV < 30 ? 'aşırı satım bölgesine yakın' : 'nötr bölgede'}; ` +
    `oynaklık ${risk === 'low' ? 'düşük' : risk === 'medium' ? 'orta' : 'yüksek'} seviyede.`;

  return {
    code,
    run_date: h[h.length - 1].date,
    horizon,
    range: { low: fc.p10, mid: mid(fc), high: fc.p90 },
    direction,
    confidence,
    risk,
    regime,
    weights: { timesfm: wT, chronos: Math.round((1 - wT) * 100) / 100 },
    indicators: {
      rsi: Math.round(rsiV * 10) / 10,
      macd_hist: Math.round(macd * 100) / 100,
      ma20_above_ma50: ma20 > ma50,
      atr_pct: Math.round(atrPct * 10) / 10,
    },
    comment,
  };
}

// ---- Tarayıcı ve sinyaller ---------------------------------------------------------------------------------

export function genScreener(f: { type?: AssetType; direction?: Direction; min_conf?: number }) {
  return genAssets(f.type).filter((a) => {
    const an = genAnalysis(a.code, 5);
    return (!f.direction || an.direction === f.direction) && (!f.min_conf || an.confidence >= f.min_conf);
  });
}

export function genSignals(): Signal[] {
  return ASSETS.flatMap((a) =>
    ([5, 20] as Horizon[]).map((hz) => ({ a, an: genAnalysis(a.code, hz) })),
  )
    .filter(({ an }) => an.direction !== 'flat' && an.confidence >= 65)
    .sort((x, y) => y.an.confidence - x.an.confidence)
    .slice(0, 5)
    .map(({ a, an }, i) => {
      const last = listItem(a).last_price;
      return {
        id: i + 1, // BIGSERIAL
        code: a.code,
        side: an.direction === 'up' ? ('buy' as const) : ('sell' as const),
        horizon: an.horizon,
        confidence: an.confidence,
        suggested_qty: null,
        stop_level: round(an.direction === 'up' ? last * 0.94 : last * 1.06, a.type),
        created_at: `${an.run_date}T21:00:00Z`,
        outcome: null,
      };
    });
}
