// Bildirim ayarları: aç/kapa (izin + push token), sessiz saatler, günlük sınır ve deneme bildirimi.
// Tercihler cihazda saklanır ve PATCH /me/profile ile sunucuya da gönderilir (sunucu sessiz saatlere uyar).
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { useState } from 'react';
import { Alert, Linking, Pressable, StyleSheet, Switch, View } from 'react-native';

import { useSignals } from '@/api/assets';
import { patchProfile } from '@/api/profile';
import { ModalShell } from '@/components/ModalShell';
import { AppText, Button, Chips, GlassCard, GlassIcon } from '@/components/ui';
import { ensurePermission, isQuietTime, registerForPush, sendTestNotification, shiftTime } from '@/lib/notifications';
import { useSettings } from '@/store/settings';
import { useTheme } from '@/theme/ThemeProvider';

const LIMITS = [1, 3, 5, 10] as const;

export default function NotificationSettings() {
  const p = useTheme();
  const { notificationsEnabled, quietHours, dailyPushLimit, pushToken, setNotifications } = useSettings();
  const signals = useSignals();
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const sync = (update: Parameters<typeof patchProfile>[0]) => patchProfile(update).catch(() => {});

  async function toggle(on: boolean) {
    if (!on) {
      setNotifications({ notificationsEnabled: false });
      return;
    }
    setBusy(true);
    try {
      const granted = await ensurePermission();
      if (!granted) {
        Alert.alert('Bildirim izni kapalı', 'Bildirimleri açmak için telefonun Ayarlar > Fon Takip bölümünden izin verin.', [
          { text: 'Vazgeç', style: 'cancel' },
          { text: 'Ayarlara git', onPress: () => Linking.openSettings() },
        ]);
        return;
      }
      const { token, reason } = await registerForPush();
      setNotifications({ notificationsEnabled: true, pushToken: token });
      setNote(token ? null : reason ?? null);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    } finally {
      setBusy(false);
    }
  }

  function setQuiet(which: 'start' | 'end', delta: number) {
    const q = quietHours ?? { start: '22:30', end: '08:00' };
    const next = { ...q, [which]: shiftTime(q[which], delta) };
    setNotifications({ quietHours: next });
    sync({ quiet_hours: next });
  }

  async function test() {
    const s = signals.data?.[0] ?? { id: 1, code: 'THYAO', side: 'buy' as const, horizon: 5 };
    if (!(await ensurePermission())) return Alert.alert('Bildirim izni gerekli');
    await sendTestNotification(s);
    setNote('3 saniye içinde bir deneme bildirimi gelecek. Uygulamayı arka plana alıp bildirime dokunun.');
  }

  const quietNow = notificationsEnabled && isQuietTime(quietHours);

  return (
    <ModalShell
      title="Bildirimler"
      subtitle="Yeni model sinyalleri için"
      footer={
        notificationsEnabled ? <Button variant="glass" title="Deneme bildirimi gönder" icon="paper-plane-outline" onPress={test} /> : null
      }
    >
      <GlassCard padding={14}>
        <View style={styles.row}>
          <GlassIcon name="notifications-outline" size={40} tone={notificationsEnabled ? 'accent' : 'neutral'} />
          <View style={styles.flex}>
            <AppText variant="bodyMedium">Sinyal bildirimleri</AppText>
            <AppText variant="caption" color="textMuted">
              İzlediğiniz varlıklarda yeni model sinyali oluşunca
            </AppText>
          </View>
          <Switch
            value={notificationsEnabled}
            onValueChange={toggle}
            disabled={busy}
            trackColor={{ true: p.accent, false: p.separator }}
            accessibilityLabel="Sinyal bildirimleri"
          />
        </View>
        {note ? (
          <View style={[styles.note, { backgroundColor: p.accentSoft }]}>
            <Ionicons name="information-circle-outline" size={16} color={p.accent} />
            <AppText variant="caption" color="textMuted" style={styles.flex}>
              {note}
            </AppText>
          </View>
        ) : null}
      </GlassCard>

      <View style={{ opacity: notificationsEnabled ? 1 : 0.5 }} pointerEvents={notificationsEnabled ? 'auto' : 'none'}>
        <AppText variant="caption" color="textMuted" style={styles.section}>
          SESSİZ SAATLER
        </AppText>
        <GlassCard padding={14}>
          <TimeRow label="Başlangıç" value={quietHours?.start ?? '22:30'} onStep={(d) => setQuiet('start', d)} />
          <View style={[styles.sep, { backgroundColor: p.separator }]} />
          <TimeRow label="Bitiş" value={quietHours?.end ?? '08:00'} onStep={(d) => setQuiet('end', d)} />
          <AppText variant="caption" color="textFaint" style={styles.mt8}>
            {quietNow ? 'Şu an sessiz saatlerdesiniz; bildirimler sabah gelir.' : 'Bu aralıkta bildirim gönderilmez.'}
          </AppText>
        </GlassCard>

        <AppText variant="caption" color="textMuted" style={styles.section}>
          GÜNLÜK EN FAZLA BİLDİRİM
        </AppText>
        <Chips
          value={dailyPushLimit}
          options={LIMITS.map((n) => ({ value: n, label: String(n) }))}
          onChange={(n) => {
            setNotifications({ dailyPushLimit: n });
            sync({ daily_push_limit: n });
          }}
          accessibilityLabel="Günlük bildirim sınırı"
        />

        <AppText variant="caption" color="textFaint" style={styles.mt12}>
          {pushToken ? 'Cihaz sunucuya kayıtlı.' : 'Sunucudan bildirim için cihaz henüz kayıtlı değil (deneme bildirimi yine çalışır).'}
        </AppText>
      </View>
    </ModalShell>
  );
}

function TimeRow({ label, value, onStep }: { label: string; value: string; onStep: (delta: number) => void }) {
  const p = useTheme();
  const Step = ({ icon, delta, a11y }: { icon: 'remove' | 'add'; delta: number; a11y: string }) => (
    <Pressable
      onPress={() => onStep(delta)}
      hitSlop={8}
      accessibilityRole="button"
      accessibilityLabel={a11y}
      style={[styles.step, { backgroundColor: p.glassFillStrong, borderColor: p.glassBorder }]}
    >
      <Ionicons name={icon} size={16} color={p.text} />
    </Pressable>
  );
  return (
    <View style={styles.row}>
      <AppText variant="bodyMedium" style={styles.flex}>
        {label}
      </AppText>
      <Step icon="remove" delta={-30} a11y={`${label} 30 dakika geri`} />
      <AppText variant="number" style={styles.time}>
        {value}
      </AppText>
      <Step icon="add" delta={30} a11y={`${label} 30 dakika ileri`} />
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  note: { flexDirection: 'row', gap: 8, padding: 10, borderRadius: 12, marginTop: 12, alignItems: 'flex-start' },
  section: { marginTop: 18, marginBottom: 8, marginLeft: 4 },
  sep: { height: StyleSheet.hairlineWidth * 2, marginVertical: 12 },
  step: { width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center', borderWidth: StyleSheet.hairlineWidth * 2 },
  time: { fontSize: 18, minWidth: 58, textAlign: 'center' },
  mt8: { marginTop: 8 },
  mt12: { marginTop: 12 },
});
