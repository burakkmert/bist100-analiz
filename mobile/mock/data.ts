// Geçici sahte veri (Hafta 1–2). Şekli shared/openapi.yaml'daki yanıtlarla aynı tutulur;
// Kişi 2'nin MOCK=1 modu hazır olunca bu dosyanın yerini API çağrıları alacak.
export interface AssetListItem {
  code: string;
  name: string;
  type: 'stock' | 'fund';
  last_price: number;
  change_pct: number;
}

export interface SignalItem {
  id: string;
  code: string;
  side: 'buy' | 'sell';
  horizon: 1 | 5 | 20;
  confidence: number;
}

export const MOCK_ASSETS: AssetListItem[] = [
  { code: 'THYAO', name: 'Türk Hava Yolları', type: 'stock', last_price: 312.5, change_pct: 1.84 },
  { code: 'ASELS', name: 'Aselsan', type: 'stock', last_price: 148.2, change_pct: -0.62 },
  { code: 'BIMAS', name: 'BİM Birleşik Mağazalar', type: 'stock', last_price: 521.0, change_pct: 0.38 },
  { code: 'KCHOL', name: 'Koç Holding', type: 'stock', last_price: 196.7, change_pct: -1.21 },
  { code: 'TUPRS', name: 'Tüpraş', type: 'stock', last_price: 167.9, change_pct: 2.45 },
  { code: 'EREGL', name: 'Ereğli Demir Çelik', type: 'stock', last_price: 47.36, change_pct: 0.0 },
  { code: 'IPB', name: 'İş Portföy BIST Banka Endeksi Fonu', type: 'fund', last_price: 4.8213, change_pct: 0.91 },
  { code: 'TTE', name: 'İş Portföy BIST Teknoloji Ağırlıklı Fon', type: 'fund', last_price: 12.0451, change_pct: -0.34 },
  { code: 'AFT', name: 'Ak Portföy Yeni Teknolojiler Fonu', type: 'fund', last_price: 3.5872, change_pct: 1.12 },
  { code: 'MAC', name: 'Marmara Capital Hisse Fonu', type: 'fund', last_price: 21.334, change_pct: 0.27 },
];

export const MOCK_SIGNALS: SignalItem[] = [
  { id: 's1', code: 'THYAO', side: 'buy', horizon: 5, confidence: 72 },
  { id: 's2', code: 'TUPRS', side: 'buy', horizon: 20, confidence: 66 },
  { id: 's3', code: 'KCHOL', side: 'sell', horizon: 5, confidence: 69 },
];

export const MOCK_BIST100 = {
  value: 10432.18,
  change_pct: 0.74,
  // Son 30 günün kapanışları (mini grafik için)
  series: [
    10012, 10055, 9988, 10021, 10102, 10140, 10096, 10180, 10211, 10175, 10230, 10198, 10260, 10301, 10285,
    10244, 10290, 10322, 10366, 10340, 10301, 10355, 10392, 10371, 10350, 10388, 10405, 10379, 10356, 10432,
  ],
};

export const MOCK_PORTFOLIO = { value: 0, change_pct: 0, positions: 0 };
