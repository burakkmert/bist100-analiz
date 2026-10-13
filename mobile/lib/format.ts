// Türkçe sayı/para biçimlendirme
import type { AssetType } from '@/api/types';

const nf2 = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const nf4 = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 4, maximumFractionDigits: 4 });

export const formatPrice = (v: number, type: AssetType = 'stock') =>
  type === 'fund' ? nf4.format(v) : nf2.format(v);
export const formatTRY = (v: number) => `₺${nf2.format(v)}`;
export const formatPct = (v: number) => `${v > 0 ? '+' : v < 0 ? '−' : ''}%${nf2.format(Math.abs(v))}`;

/** Grafik eksen etiketi: büyüklüğe göre ondalık sayısı */
export const formatAxis = (v: number) => {
  const digits = v >= 1000 ? 0 : v >= 10 ? 1 : v >= 1 ? 2 : 3;
  return new Intl.NumberFormat('tr-TR', { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(v);
};

const MONTHS = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara'];
/** "2026-10-07" → "7 Eki 2026" (Intl'in ay adları bazı Android'lerde eksik olabildiği için elle) */
export const formatDate = (iso: string) => {
  const [y, m, d] = iso.split('-').map(Number);
  return `${d} ${MONTHS[m - 1]} ${y}`;
};
