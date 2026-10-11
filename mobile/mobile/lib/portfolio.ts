// Portföy hesapları: güncel değer, kâr/zarar, günlük değişim.
import { useMemo } from 'react';

import { useAssets } from '@/api/assets';
import type { AssetListItem } from '@/api/types';
import { usePortfolio, type Position } from '@/store/portfolio';

export interface PositionView extends Position {
  asset: AssetListItem | undefined;
  /** Açık pozisyonda güncel fiyat, kapalıda satış fiyatı */
  price: number;
  cost: number;
  value: number;
  pnl: number;
  pnlPct: number;
  /** Bugünkü değişim (yalnızca açık pozisyonlar) */
  dayPnl: number;
  open: boolean;
}

export function usePortfolioView() {
  const positions = usePortfolio((s) => s.positions);
  const assets = useAssets();

  return useMemo(() => {
    const byCode = new Map((assets.data ?? []).map((a) => [a.code, a]));
    const views: PositionView[] = positions.map((p) => {
      const asset = byCode.get(p.code);
      const open = p.sell_price === null;
      const price = open ? (asset?.last_price ?? p.buy_price) : (p.sell_price as number);
      const cost = p.qty * p.buy_price;
      const value = p.qty * price;
      const prevPrice = asset ? asset.last_price / (1 + asset.change_pct / 100) : price;
      return {
        ...p,
        asset,
        price,
        cost,
        value,
        pnl: value - cost,
        pnlPct: cost ? ((value - cost) / cost) * 100 : 0,
        dayPnl: open && asset ? p.qty * (asset.last_price - prevPrice) : 0,
        open,
      };
    });

    const openOnes = views.filter((v) => v.open);
    const closed = views.filter((v) => !v.open);
    const openValue = openOnes.reduce((a, v) => a + v.value, 0);
    const openCost = openOnes.reduce((a, v) => a + v.cost, 0);
    const dayPnl = openOnes.reduce((a, v) => a + v.dayPnl, 0);
    const realized = closed.reduce((a, v) => a + v.pnl, 0);

    return {
      loading: assets.isLoading,
      open: openOnes,
      closed,
      summary: {
        value: openValue,
        unrealized: openValue - openCost,
        unrealizedPct: openCost ? ((openValue - openCost) / openCost) * 100 : 0,
        dayPnl,
        dayPct: openValue - dayPnl ? (dayPnl / (openValue - dayPnl)) * 100 : 0,
        realized,
        count: openOnes.length,
      },
    };
  }, [positions, assets.data, assets.isLoading]);
}

// ---- Tarih yardımcıları (form için GG.AA.YYYY) ----------------------------------------------------

export const todayISO = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

export const isoToTr = (iso: string) => {
  const [y, m, d] = iso.split('-');
  return `${d}.${m}.${y}`;
};

/** "07.10.2026" → "2026-10-07"; geçersizse null */
export const trToIso = (tr: string): string | null => {
  const m = tr.trim().match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$/);
  if (!m) return null;
  const [, d, mo, y] = m;
  const date = new Date(Number(y), Number(mo) - 1, Number(d));
  if (date.getDate() !== Number(d) || date.getMonth() !== Number(mo) - 1) return null;
  if (date.getTime() > Date.now()) return null; // gelecek tarih olmaz
  return `${y}-${mo.padStart(2, '0')}-${d.padStart(2, '0')}`;
};

/** "1.234,56" ya da "1234.56" → 1234.56 */
export const parseNumber = (s: string): number | null => {
  const t = s.trim().replace(/\s/g, '');
  if (!t) return null;
  const normalized = t.includes(',') ? t.replace(/\./g, '').replace(',', '.') : t;
  const n = Number(normalized);
  return Number.isFinite(n) ? n : null;
};
