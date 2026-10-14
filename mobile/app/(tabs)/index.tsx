// Ana sayfa: portföy özeti, BIST100 kartı, bugünün model sinyalleri.
import { useState } from 'react';
import { router } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';

import { SignalCard } from '@/components/SignalCard';
import { Sparkline } from '@/components/Sparkline';
import { AppText, Badge, Disclaimer, GlassCard, GlassIcon, Screen, Skeleton } from '@/components/ui';
import { useIndex, useSignals } from '@/api/assets';
import { formatPct, formatPrice, formatTRY } from '@/lib/format';
import { usePortfolioView } from '@/lib/portfolio';
import { useSettings } from '@/store/settings';
import { useAuth } from '@/store/auth';
import { useTheme } from '@/theme/ThemeProvider';

function greeting() {
  const h = new Date().getHours();
  if (h < 6) return 'İyi geceler';
  if (h < 12) return 'Günaydın';
  if (h < 18) return 'İyi günler';
  return 'İyi akşamlar';
}

export default function Home() {
  const p = useTheme();
  const email = useAuth((s) => s.user?.email);
  const [sparkW, setSparkW] = useState(0);
  const portfolio = usePortfolioView();
  const notificationsOn = useSettings((s) => s.notificationsEnabled);
  const ps = portfolio.summary;
  const index = useIndex();
  const signals = useSignals();
  const bist = index.data;
  const bistUp = (bist?.change_pct ?? 0) >= 0;

  return (
    <Screen tabBarSpace>
      <Animated.View entering={FadeInDown.duration(400)} style={styles.header}>
        <View style={styles.flex}>
          <AppText color="textMuted">{greeting()}</AppText>
          <AppText variant="title" numberOfLines={1}>
            {email?.split('@')[0] ?? 'Hoş geldiniz'}
          </AppText>
        </View>
        <Pressable onPress={() => router.push('/notifications')} accessibilityRole="button" accessibilityLabel="Bildirim ayarları" hitSlop={6}>
          <GlassIcon name={notificationsOn ? 'notifications' : 'notifications-outline'} size={42} tone={notificationsOn ? 'accent' : 'neutral'} />
        </Pressable>
      </Animated.View>

      {/* Portföy özeti */}
      <Animated.View entering={FadeInDown.delay(60).duration(400)}>
        <Pressable onPress={() => router.push('/portfolio')} accessibilityRole="button" accessibilityLabel="Portföye git">
          <GlassCard padding={20}>
            <AppText variant="caption" color="textMuted">
              PORTFÖY DEĞERİ
            </AppText>
            <AppText variant="display" style={styles.value}>
              {formatTRY(ps.value)}
            </AppText>
            {ps.count === 0 ? (
              <AppText color="textMuted">
                Henüz açık pozisyonunuz yok. Bir varlığın detayında "Aldım" ile işlemlerinizi kaydedebilirsiniz.
              </AppText>
            ) : (
              <AppText style={{ color: ps.dayPnl > 0 ? p.up : ps.dayPnl < 0 ? p.down : p.textMuted }}>
                Bugün {ps.dayPnl >= 0 ? '+' : '−'}
                {formatTRY(Math.abs(ps.dayPnl))} ({formatPct(ps.dayPct)}) · {ps.count} pozisyon
              </AppText>
            )}
          </GlassCard>
        </Pressable>
      </Animated.View>

      {/* BIST100 */}
      <Animated.View entering={FadeInDown.delay(120).duration(400)}>
        <GlassCard>
          <View style={styles.rowBetween}>
            <View>
              <AppText variant="heading">BIST 100</AppText>
              <AppText variant="number" style={{ color: p.text, fontSize: 20, marginTop: 2 }}>
                {bist ? formatPrice(bist.last_price) : '—'}
              </AppText>
            </View>
            {bist ? <Badge label={formatPct(bist.change_pct)} tone={bistUp ? 'up' : 'down'} /> : null}
          </View>
          <View style={styles.spark} onLayout={(e) => setSparkW(e.nativeEvent.layout.width)}>
            {bist ? (
              <Sparkline data={bist.series} width={sparkW} height={64} color={bistUp ? p.up : p.down} />
            ) : (
              <Skeleton height={64} radius={10} />
            )}
          </View>
          <AppText variant="caption" color="textFaint">
            Son 30 gün
          </AppText>
        </GlassCard>
      </Animated.View>

      {/* Sinyaller */}
      <Animated.View entering={FadeInDown.delay(180).duration(400)} style={styles.section}>
        <AppText variant="heading">Bugünün model sinyalleri</AppText>
        {signals.isLoading ? (
          [0, 1, 2].map((i) => <Skeleton key={i} height={96} radius={22} />)
        ) : signals.data && signals.data.length > 0 ? (
          signals.data.map((s) => <SignalCard key={s.id} signal={s} />)
        ) : (
          <AppText color="textMuted">Bugün profilinize uyan model sinyali yok.</AppText>
        )}
        <Disclaimer />
      </Animated.View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  flex: { flex: 1 },
  value: { marginVertical: 4 },
  rowBetween: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' },
  spark: { marginVertical: 12 },
  section: { gap: 10 },
});
