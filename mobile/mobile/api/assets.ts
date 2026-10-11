// Varlık verileri: MOCK modunda üreticiden, değilse Kişi 2'nin API'sinden.
// Ekranlar yalnızca aşağıdaki hook'ları kullanır; veri kaynağı değişince ekran kodu değişmez.
import { useQuery } from '@tanstack/react-query';

import * as mock from '@/mock/generator';
import { api, USE_MOCK } from './client';
import type {
  Analysis,
  AssetListItem,
  AssetType,
  Forecast,
  Horizon,
  PricePoint,
  ScreenerFilter,
  Signal,
} from './types';

/** Mock modunda gerçekçi ağ gecikmesi (yükleniyor durumlarını görmek için) */
const delay = (ms = 250 + Math.random() * 250) => new Promise((r) => setTimeout(r, ms));
const qs = (o: Record<string, string | number | undefined>) =>
  Object.entries(o)
    .filter(([, v]) => v !== undefined && v !== '')
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
    .join('&');

export async function fetchAssets(type?: AssetType, q?: string): Promise<AssetListItem[]> {
  if (USE_MOCK) return delay().then(() => mock.genAssets(type, q));
  return api(`/assets?${qs({ type, q })}`);
}

export async function fetchHistory(code: string, days = 365): Promise<PricePoint[]> {
  if (USE_MOCK) return delay().then(() => mock.genHistory(code).slice(-days));
  return api(`/assets/${code}/history?days=${days}`);
}

export async function fetchForecast(code: string): Promise<Forecast> {
  if (USE_MOCK) return delay().then(() => mock.genForecast(code));
  return api(`/assets/${code}/forecast`);
}

export async function fetchAnalysis(code: string, horizon: Horizon): Promise<Analysis> {
  if (USE_MOCK) return delay().then(() => mock.genAnalysis(code, horizon));
  return api(`/assets/${code}/analysis?horizon=${horizon}`);
}

export async function fetchScreener(f: ScreenerFilter): Promise<AssetListItem[]> {
  if (USE_MOCK) return delay().then(() => mock.genScreener(f));
  return api(`/screener?${qs({ type: f.type, direction: f.direction, min_conf: f.min_conf })}`);
}

export async function fetchSignals(): Promise<Signal[]> {
  if (USE_MOCK) return delay().then(() => mock.genSignals());
  return api('/signals?status=open');
}

// ---- Hook'lar ----------------------------------------------------------------------------------

export const useAssets = (type?: AssetType, q?: string) =>
  useQuery({ queryKey: ['assets', type, q], queryFn: () => fetchAssets(type, q) });

export const useScreener = (f: ScreenerFilter) =>
  useQuery({ queryKey: ['screener', f], queryFn: () => fetchScreener(f) });

/** 5 yıllık seriyi bir kez alır; aralık (1A/3A/1Y/5Y) seçimi istemcide yapılır */
export const useHistory = (code: string) =>
  useQuery({ queryKey: ['history', code], queryFn: () => fetchHistory(code, 1260), staleTime: 10 * 60_000 });

export const useForecast = (code: string) =>
  useQuery({ queryKey: ['forecast', code], queryFn: () => fetchForecast(code), staleTime: 10 * 60_000 });

export const useAnalysis = (code: string, horizon: Horizon) =>
  useQuery({ queryKey: ['analysis', code, horizon], queryFn: () => fetchAnalysis(code, horizon) });

export const useSignals = () => useQuery({ queryKey: ['signals'], queryFn: fetchSignals });

/** Ana sayfadaki BIST 100 kartı (API'de ayrı uç yok; XU100 bir varlık gibi istenir) */
export const useIndex = () =>
  useQuery({
    queryKey: ['index', 'XU100'],
    queryFn: async () => {
      if (USE_MOCK) return delay().then(() => mock.genIndex());
      const h = await fetchHistory('XU100', 30);
      const last = h[h.length - 1].close;
      const prev = h[h.length - 2].close;
      return { code: 'XU100', name: 'BIST 100', last_price: last, change_pct: ((last - prev) / prev) * 100, series: h.map((p) => p.close) };
    },
  });

/** Varlık adı/fiyatı (listeden; detay ekranı başlığı için) */
export const useAsset = (code: string) =>
  useQuery({
    queryKey: ['asset', code],
    queryFn: async () => {
      if (USE_MOCK) return delay(120).then(() => mock.genAsset(code));
      const list = await fetchAssets(undefined, code);
      return list.find((a) => a.code === code) ?? null;
    },
  });
