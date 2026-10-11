// Ayarlar: tema, risk profili, hesap.
import { Ionicons } from '@expo/vector-icons';
import Constants from 'expo-constants';
import { Alert, Pressable, StyleSheet, View } from 'react-native';

import { ThemeToggle } from '@/components/ThemeToggle';
import { AppText, GlassCard, GlassIcon, Screen, type IconName, type Tone } from '@/components/ui';
import { isDemoMode } from '@/lib/supabase';
import { useAuth } from '@/store/auth';
import { useSettings } from '@/store/settings';
import { useTheme } from '@/theme/ThemeProvider';

const PROFILE_LABEL = { cautious: 'Temkinli', balanced: 'Dengeli', aggressive: 'Atak' } as const;

function Row({
  icon,
  tone = 'accent',
  title,
  detail,
  onPress,
  destructive,
}: {
  icon: IconName;
  tone?: Tone;
  title: string;
  detail?: string;
  onPress?: () => void;
  destructive?: boolean;
}) {
  const p = useTheme();
  return (
    <Pressable onPress={onPress} disabled={!onPress} style={styles.row} accessibilityRole="button">
      <GlassIcon name={icon} size={36} tone={destructive ? 'down' : tone} />
      <AppText variant="bodyMedium" style={[styles.flex, destructive && { color: p.down }]}>
        {title}
      </AppText>
      {detail ? <AppText color="textMuted">{detail}</AppText> : null}
      {onPress ? <Ionicons name="chevron-forward" size={18} color={p.textFaint} /> : null}
    </Pressable>
  );
}

export default function Settings() {
  const p = useTheme();
  const { themePreference, setThemePreference, riskProfile, resetRiskProfile } = useSettings();
  const { user, signOut } = useAuth();

  const Sep = () => <View style={[styles.sep, { backgroundColor: p.separator }]} />;

  return (
    <Screen tabBarSpace>
      <AppText variant="title">Ayarlar</AppText>

      <AppText variant="caption" color="textMuted" style={styles.section}>
        GÖRÜNÜM
      </AppText>
      <GlassCard padding={4}>
        <View style={styles.row}>
          <GlassIcon name={p.name === 'dark' ? 'moon-outline' : 'sunny-outline'} size={36} tone="neutral" />
          <View style={styles.flex}>
            <AppText variant="bodyMedium">{p.name === 'dark' ? 'Koyu tema' : 'Açık tema'}</AppText>
            {themePreference === 'system' ? (
              <AppText variant="caption" color="textFaint">
                Telefonun ayarına uyuyor
              </AppText>
            ) : (
              <Pressable onPress={() => setThemePreference('system')} hitSlop={6}>
                <AppText variant="caption" color="accent">
                  Telefonun ayarına dön
                </AppText>
              </Pressable>
            )}
          </View>
          <ThemeToggle />
        </View>
      </GlassCard>

      <AppText variant="caption" color="textMuted" style={styles.section}>
        YATIRIM PROFİLİ
      </AppText>
      <GlassCard padding={4}>
        <Row
          icon="speedometer-outline"
          title="Risk profili"
          detail={riskProfile ? PROFILE_LABEL[riskProfile] : '—'}
          onPress={() =>
            Alert.alert('Anketi yeniden yap', 'Risk profili anketine dönülecek.', [
              { text: 'Vazgeç', style: 'cancel' },
              { text: 'Devam', onPress: resetRiskProfile },
            ])
          }
        />
        <Sep />
        <Row icon="notifications-outline" title="Bildirimler" detail="Yakında" tone="neutral" />
      </GlassCard>

      <AppText variant="caption" color="textMuted" style={styles.section}>
        HESAP
      </AppText>
      <GlassCard padding={4}>
        <Row icon="person-circle-outline" title={user?.email ?? 'Misafir'} detail={isDemoMode ? 'Demo' : undefined} tone="neutral" />
        <Sep />
        <Row icon="log-out-outline" title="Çıkış yap" destructive onPress={signOut} />
      </GlassCard>

      <AppText variant="caption" color="textFaint" style={styles.version}>
        Fon Takip · sürüm {Constants.expoConfig?.version ?? '0.1.0'}
      </AppText>
    </Screen>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 12 },
  flex: { flex: 1 },
  sep: { height: StyleSheet.hairlineWidth * 2, marginLeft: 60 },
  section: { marginBottom: -6, marginLeft: 4 },
  version: { textAlign: 'center', marginTop: 8 },
});
