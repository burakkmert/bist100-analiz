// PATCH /me/profile — risk profili, bütçe, sessiz saatler, günlük bildirim sınırı (shared/openapi.yaml → ProfileUpdate).
// Yalnızca gönderilen alanlar güncellenir; bir alanı silmek için null gönderilir.
import type { ProfileOut, ProfileUpdate } from './types';
import { api, USE_MOCK } from './client';

export async function patchProfile(update: ProfileUpdate): Promise<Partial<ProfileOut>> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 400)); // gerçekçi gecikme
    return update as Partial<ProfileOut>;
  }
  return api<ProfileOut>('/me/profile', { method: 'PATCH', body: JSON.stringify(update) });
}

/** POST /devices/push-token — Expo push token'ını sunucuya kaydeder (Kişi 2 bildirimleri buna gönderir). */
export async function registerPushTokenOnServer(token: string, platform: 'ios' | 'android'): Promise<void> {
  if (USE_MOCK) return;
  await api<void>('/devices/push-token', { method: 'POST', body: JSON.stringify({ token, platform }) });
}
