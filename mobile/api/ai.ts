// POST /ai/chat — yapay zekâ asistanı (backend/app/ai/router.py).
// İstek: { messages: [{role, content}], image?: "data:image/...;base64,...", context?: {screen, code, horizon} }
// Yanıt (Accept: text/event-stream): satır satır  data: {"delta": "..."}  ...  data: {"done": true, "replace"?: "..."}
// MOCK=1 iken aşağıdaki sahte yanıtlar aynı biçimde kelime kelime akıtılır.
import { fetch as expoFetch } from 'expo/fetch';

import type { ScreenContext } from '@/store/assistant';
import { useAuth } from '@/store/auth';
import { USE_AI_MOCK } from './client';

const BASE_URL = process.env.EXPO_PUBLIC_API_URL?.replace(/\/$/, '') ?? '';

export interface ChatTurn {
  role: 'user' | 'assistant';
  content: string;
}

interface StreamOptions {
  messages: ChatTurn[];
  image?: string | null;
  context?: ScreenContext | null;
  /** Her yeni metin parçasında çağrılır (o ana kadarki tam metinle) */
  onText: (full: string) => void;
  signal?: AbortSignal;
}

/** Cevabı akış hâlinde alır; bitince son (gerekirse korkulukla düzeltilmiş) metni döner. */
export async function streamAI({ messages, image, context, onText, signal }: StreamOptions): Promise<string> {
  if (USE_AI_MOCK) {
    await sleep(500 + Math.random() * 400); // "düşünüyor"
    const reply = mockReply(messages[messages.length - 1]?.content ?? '', !!image, context ?? null);
    let full = '';
    for (const part of reply.match(/\S+\s*/g) ?? []) {
      if (signal?.aborted) break;
      full += part;
      onText(full);
      await sleep(18 + Math.random() * 30);
    }
    return full;
  }

  const token = useAuth.getState().accessToken;
  let res: Awaited<ReturnType<typeof expoFetch>>;
  try {
    res = await expoFetch(`${BASE_URL}/ai/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ messages, image: image ?? undefined, context: context ?? undefined }),
      signal,
    });
  } catch {
    throw new Error('Yapay zekâ sunucusuna ulaşılamadı. Bilgisayardaki sunucu açık mı, telefon aynı Wi-Fi\'da mı?');
  }
  if (res.status === 429) throw new Error('Ücretsiz kullanım sınırına ulaşıldı. Bir dakika sonra tekrar deneyin.');
  if (!res.ok || !res.body) throw new Error(`Sunucu yanıt vermedi (${res.status}).`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let full = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split('\n\n');
    buffer = events.pop() ?? '';
    for (const ev of events) {
      const line = ev.split('\n').find((l) => l.startsWith('data:'));
      if (!line) continue;
      const data = JSON.parse(line.slice(5).trim()) as { delta?: string; done?: boolean; replace?: string; error?: string };
      if (data.error) throw new Error(data.error);
      if (data.delta) {
        full += data.delta;
        onText(full);
      }
      if (data.replace !== undefined) {
        full = data.replace;
        onText(full);
      }
    }
  }
  return full;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// ---- Sahte yanıtlar: terim sözlüğü + görsel algılama taklidi -------------------------------

const GLOSSARY: { keys: string[]; text: string }[] = [
  {
    keys: ['rsi'],
    text:
      'RSI (Göreceli Güç Endeksi), son 14 gündeki yükseliş ve düşüşlerin gücünü 0–100 arasında ölçer. ' +
      '70 üzeri genellikle "aşırı alım", 30 altı "aşırı satım" bölgesi olarak yorumlanır. Tek başına bir karar ' +
      'göstergesi değildir; trend ve hacimle birlikte değerlendirilir.',
  },
  {
    keys: ['macd'],
    text:
      'MACD, kısa (12 gün) ve uzun (26 gün) hareketli ortalamalar arasındaki farktır. MACD çizgisinin sinyal ' +
      'çizgisini yukarı kesmesi yükseliş ivmesi, aşağı kesmesi düşüş ivmesi olarak okunur.',
  },
  {
    keys: ['volatil', 'oynak'],
    text:
      'Volatilite, fiyatın ne kadar sert dalgalandığını gösterir. Yüksek volatilite, hem kazanç hem kayıp ' +
      'aralığının geniş olduğu anlamına gelir. Tahmin bandının genişliği de bu yüzden değişir.',
  },
  {
    keys: ['güven', 'guven', 'confidence'],
    text:
      'Güven skoru (0–100), modelin bu yönü geçmiş benzer durumlarda ne kadar tutarlı bulduğunu gösterir. ' +
      'Kesinlik değildir: 70 güvenli bir sinyal de yanılabilir.',
  },
  {
    keys: ['sinyal', 'signal'],
    text:
      'Model sinyali, istatistiksel modelin belirli bir ufukta (1, 5 veya 20 gün) fiyat yönü için ürettiği ' +
      'olasılıksal bir çıktıdır. Uygulama işlem yapmaz; kararı ve sorumluluğu size bırakır.',
  },
  {
    keys: ['risk profil', 'temkinli', 'dengeli', 'atak'],
    text:
      'Risk profiliniz, hangi güven seviyesinin üstündeki sinyallerin gösterileceğini ve önerilen pozisyon ' +
      'büyüklüğünü belirler. Temkinli: güven ≥ 75, Dengeli: ≥ 65, Atak: ≥ 55.',
  },
  {
    keys: ['fon', 'tefas'],
    text:
      'TEFAS fonlarının fiyatı gün içinde değil, günde bir kez açıklanır. Bu yüzden fon grafiklerinde mum ' +
      'yerine çizgi grafik kullanılır.',
  },
  {
    keys: ['bist', 'endeks'],
    text: 'BIST 100, Borsa İstanbul\'daki en büyük 100 şirketin fiyat hareketlerini tek bir sayıda özetleyen endekstir.',
  },
];

function mockReply(question: string, hasImage: boolean, ctx: ScreenContext | null): string {
  const q = question.toLocaleLowerCase('tr-TR');
  if (ctx?.code && /(bu|neden|sinyal|grafik|ne anlat)/.test(q) && !hasImage) {
    return (
      `${ctx.code} detay ekranından soruyorsunuz. (Demo yanıtı — gerçek sürümde bu varlığın model analizi, ` +
      'göstergeleri ve tahmin aralığı sunucudan alınıp yoruma eklenecek.)\n\n' +
      'Detay ekranındaki güven skoru, modellerin bu yönde ne kadar uzlaştığını; mavi koni ise fiyatın %80 ' +
      'olasılıkla kalması beklenen aralığı gösterir.'
    );
  }
  const hit = GLOSSARY.find((g) => g.keys.some((k) => q.includes(k)));

  if (hasImage) {
    return (
      'Görseli aldım. (Demo yanıtı — gerçek görsel yorumu backend bağlanınca çalışacak.)\n\n' +
      'Bir grafikte genellikle şunlara bakarım: genel trend yönü, son dönemde destek/direnç gibi çalışan ' +
      'fiyat seviyeleri, hacimdeki değişim ve tahmin bandının genişliği. ' +
      (hit ? `\n\n${hit.text}` : 'Görselde özellikle merak ettiğiniz bir kısım varsa yazın, ona odaklanayım.')
    );
  }
  if (hit) return hit.text;
  if (q.includes('ekran')) {
    return (
      'Bu ekranı anlamama yardımcı olması için balona dokunduğunuz anki ekranın görüntüsünü ekleyebilirsiniz ' +
      '(ataç simgesi → "Az önceki ekran"). Sonra hangi kısmı anlamadığınızı yazın.'
    );
  }
  return (
    'Demo modundayım, şimdilik terimleri (RSI, MACD, volatilite, güven skoru, sinyal…) açıklayabiliyorum. ' +
    'Backend bağlandığında grafik ve ekran görüntülerini de yorumlayacağım.'
  );
}
