// Backend istemcisi. Her isteğe Supabase token'ı "Authorization: Bearer" olarak eklenir.
// EXPO_PUBLIC_API_URL boşsa veya EXPO_PUBLIC_MOCK=1 ise istekler gönderilmez; mock veri kullanılır.
// Not: 3–4. haftada shared/openapi.yaml'dan openapi-typescript ile tipler üretilip burada kullanılacak.
import { useAuth } from '@/store/auth';

const BASE_URL = process.env.EXPO_PUBLIC_API_URL?.replace(/\/$/, '') ?? '';
export const USE_MOCK = !BASE_URL || process.env.EXPO_PUBLIC_MOCK === '1';
/**
 * Yapay zekâ için ayrı anahtar: hisse verileri sahte kalırken asistan gerçek sunucuya (Gemini) bağlanabilsin.
 * EXPO_PUBLIC_API_URL doluysa ve EXPO_PUBLIC_AI_MOCK=1 değilse asistan sunucuya gider.
 */
export const USE_AI_MOCK = !BASE_URL || process.env.EXPO_PUBLIC_AI_MOCK === '1';

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = useAuth.getState().accessToken;
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new ApiError(res.status, text || `İstek başarısız (${res.status})`);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}
