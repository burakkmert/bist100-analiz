// Bildirimler (Görev 8): izin, push token, deneme bildirimi ve bildirime dokununca doğru ekranı açma.
//
// • Sunucudan gelen (uzak) bildirimler Kişi 2'nin gece işiyle gönderilir; bunun için cihazın Expo push
//   token'ı POST /devices/push-token ile kaydedilir. Token almak için EAS proje kimliği gerekir
//   (`npx eas init` sonrası app.json → extra.eas.projectId). Yoksa token alınmaz; uygulama yine çalışır.
// • Yerel "deneme bildirimi" Expo Go'da da çalışır: bildirime dokununca sinyal ekranı açılır.
// • Bildirim içeriğinde { signal_id, code } gelir; dokununca /signal/[id] açılır.
import Constants from 'expo-constants';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import { router } from 'expo-router';
import { useEffect } from 'react';
import { Platform } from 'react-native';

import { registerPushTokenOnServer } from '@/api/profile';
import type { QuietHours } from '@/api/types';
import { useSettings } from '@/store/settings';

export const ANDROID_CHANNEL = 'signals';

// Uygulama açıkken gelen bildirim de üstte görünsün
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

async function ensureAndroidChannel() {
  if (Platform.OS !== 'android') return;
  await Notifications.setNotificationChannelAsync(ANDROID_CHANNEL, {
    name: 'Model sinyalleri',
    importance: Notifications.AndroidImportance.HIGH,
    vibrationPattern: [0, 200, 120, 200],
  });
}

/** İzin ister; verildiyse true. Kullanıcı daha önce reddettiyse sistem penceresi yeniden açılmaz. */
export async function ensurePermission(): Promise<boolean> {
  await ensureAndroidChannel();
  const current = await Notifications.getPermissionsAsync();
  if (current.granted) return true;
  if (!current.canAskAgain) return false;
  const asked = await Notifications.requestPermissionsAsync();
  return asked.granted;
}

/** Expo push token'ını alıp sunucuya kaydeder. Simülatörde / EAS kimliği yoksa null döner (hata değil). */
export async function registerForPush(): Promise<{ token: string | null; reason?: string }> {
  if (!Device.isDevice) return { token: null, reason: 'Simülatörde push token alınamaz.' };
  const projectId =
    (Constants.expoConfig?.extra as { eas?: { projectId?: string } } | undefined)?.eas?.projectId ??
    Constants.easConfig?.projectId;
  if (!projectId) return { token: null, reason: 'EAS proje kimliği yok (npx eas init ile eklenecek).' };
  try {
    const { data } = await Notifications.getExpoPushTokenAsync({ projectId });
    await registerPushTokenOnServer(data, Platform.OS === 'ios' ? 'ios' : 'android').catch(() => {});
    return { token: data };
  } catch (e) {
    return { token: null, reason: e instanceof Error ? e.message : 'Token alınamadı.' };
  }
}

/** 3 sn sonra yerel bir model sinyali bildirimi gösterir (Expo Go'da da çalışır). */
export async function sendTestNotification(signal: { id: number; code: string; side: 'buy' | 'sell'; horizon: number }) {
  await ensureAndroidChannel();
  const dir = signal.side === 'buy' ? 'yükseliş' : 'düşüş';
  await Notifications.scheduleNotificationAsync({
    content: {
      title: `${signal.code} · yeni model sinyali`,
      body: `${signal.horizon} günlük ufukta ${dir} yönlü sinyal. Ayrıntılar için dokunun.`,
      data: { signal_id: signal.id, code: signal.code },
      sound: true,
    },
    trigger: {
      type: Notifications.SchedulableTriggerInputTypes.TIME_INTERVAL,
      seconds: 3,
      channelId: ANDROID_CHANNEL,
    },
  });
}

let handledResponseId: string | null = null;

function openFromData(data: Record<string, unknown> | undefined) {
  const id = data?.signal_id;
  if (id !== undefined && id !== null && String(id) !== '') router.push(`/signal/${String(id)}`);
  else if (typeof data?.code === 'string') router.push(`/asset/${data.code}`);
}

/**
 * Bildirime dokununca sinyal ekranını açar. Uygulama kapalıyken dokunulduysa açılışta son bildirim işlenir.
 * Yalnızca giriş yapılmış ve ilk kurulum bitmişken çağrılmalı (kök yerleşimde).
 */
export function useNotificationRouting(enabled: boolean) {
  const last = Notifications.useLastNotificationResponse();

  useEffect(() => {
    if (!enabled || !last) return;
    const id = last.notification.request.identifier;
    if (id === handledResponseId) return; // aynı bildirim ekran yeniden kurulunca tekrar açılmasın
    handledResponseId = id;
    openFromData(last.notification.request.content.data as Record<string, unknown>);
  }, [enabled, last]);

  useEffect(() => {
    if (!enabled) return;
    const sub = Notifications.addNotificationResponseReceivedListener((r) => {
      handledResponseId = r.notification.request.identifier;
      openFromData(r.notification.request.content.data as Record<string, unknown>);
    });
    return () => sub.remove();
  }, [enabled]);
}

/** Açılışta: bildirimler açıksa token'ı tazele (cihaz/proje değişmiş olabilir). */
export async function refreshPushTokenIfEnabled() {
  const s = useSettings.getState();
  if (!s.notificationsEnabled) return;
  const perm = await Notifications.getPermissionsAsync();
  if (!perm.granted) return s.setNotifications({ notificationsEnabled: false });
  const { token } = await registerForPush();
  if (token && token !== s.pushToken) s.setNotifications({ pushToken: token });
}

// ---- Sessiz saatler -------------------------------------------------------------------------------

const toMin = (hhmm: string) => {
  const [h, m] = hhmm.split(':').map(Number);
  return h * 60 + m;
};

/** Verilen an sessiz saatlerin içinde mi? Gece yarısını aşan aralıklar (22:30–08:00) desteklenir. */
export function isQuietTime(q: QuietHours | null, now = new Date()): boolean {
  if (!q) return false;
  const t = now.getHours() * 60 + now.getMinutes();
  const a = toMin(q.start);
  const b = toMin(q.end);
  return a <= b ? t >= a && t < b : t >= a || t < b;
}

/** "22:30" + 30 dk → "23:00" (gün sınırında döner) */
export function shiftTime(hhmm: string, minutes: number): string {
  const t = (toMin(hhmm) + minutes + 24 * 60) % (24 * 60);
  return `${String(Math.floor(t / 60)).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}`;
}
