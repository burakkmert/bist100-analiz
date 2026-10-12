// POST /ai/chart-read — grafik görüntüsünü yapay zekâya yorumlatır (backend/app/ai/chart_read.py).
// İstek: { image: "data:image/...;base64,...", code?: "THYAO" }
// Yanıt: ChartReading (aşağıda). AI_MOCK=1 iken örnek bir yorum döner.
import { useAuth } from '@/store/auth';
import { USE_AI_MOCK } from './client';

export interface ChartReading {
  trend: 'up' | 'down' | 'flat';
  supports: number[];
  resistances: number[];
  pattern: string | null;
  indicators_note: string | null;
  summary: string;
  confidence_note: string;
}

const BASE_URL = process.env.EXPO_PUBLIC_API_URL?.replace(/\/$/, '') ?? '';

export async function readChart(image: string, code?: string | null): Promise<ChartReading> {
  if (USE_AI_MOCK) {
    await new Promise((r) => setTimeout(r, 1600));
    return {
      trend: 'up',
      supports: [298.5, 285],
      resistances: [320, 335],
      pattern: 'Yükselen kanal',
      indicators_note: 'RSI nötr bölgede; kısa vade ortalaması uzun vadenin üzerinde.',
      summary:
        'Fiyat son dönemde dipleri ve tepeleri yükselerek hareket ediyor. 320 seviyesi birkaç kez test edilmiş bir direnç gibi görünüyor. (Demo yorumu.)',
      confidence_note: code
        ? 'Demo modunda; gerçek sürümde sayısal veriyle karşılaştırılacak.'
        : 'Yalnızca görsel desen yorumu; sayısal veriyle karşılaştırılmadı.',
    };
  }

  const token = useAuth.getState().accessToken;
  const controller = new AbortController();
  // Sunucu en fazla ~75 sn içinde cevap ya da anlaşılır bir hata döndürür; bu süre onun üstünde kalmalı
  const timer = setTimeout(() => controller.abort(), 100_000);
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}/ai/chart-read`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify({ image, code: code ?? undefined }),
      signal: controller.signal,
    });
  } catch {
    if (controller.signal.aborted) throw new Error('Yapay zekâ zamanında yanıt vermedi. Biraz sonra tekrar deneyin.');
    throw new Error('Yapay zekâ sunucusuna ulaşılamadı. Bilgisayardaki sunucu açık mı, telefon aynı ağda mı?');
  } finally {
    clearTimeout(timer);
  }
    if (!res.ok) {
    let detail = '';
    try {
      detail = ((await res.json()) as { detail?: string }).detail ?? '';
    } catch {}
    throw new Error(detail || `Grafik yorumlanamadı (${res.status}).`);
  }
  return (await res.json()) as ChartReading;
}
