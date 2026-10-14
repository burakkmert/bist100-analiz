// Model sinyali kartı. Dil kuralı: emir kipi yok → "yükseliş yönlü model sinyali".
// Dokununca sinyal detayına gider (neden bu sinyal, stop seviyesi, "Aldım").
import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';

import type { Signal } from '@/api/types';
import { AppText, Badge, GlassCard, GlassIcon } from '@/components/ui';
import { useTheme } from '@/theme/ThemeProvider';

export function SignalCard({ signal }: { signal: Pick<Signal, 'id' | 'code' | 'side' | 'horizon' | 'confidence'> }) {
  const p = useTheme();
  const up = signal.side === 'buy';
  return (
    <Pressable
      onPress={() => router.push(`/signal/${signal.id}`)}
      accessibilityRole="button"
      accessibilityLabel={`${signal.code}, ${signal.horizon} günlük ${up ? 'yükseliş' : 'düşüş'} yönlü model sinyali, güven ${signal.confidence}`}
      style={({ pressed }) => ({ opacity: pressed ? 0.85 : 1 })}
    >
      <GlassCard padding={14}>
        <View style={styles.row}>
          <GlassIcon name={up ? 'trending-up' : 'trending-down'} tone={up ? 'up' : 'down'} size={42} />
          <View style={styles.flex}>
            <AppText variant="heading">{signal.code}</AppText>
            <AppText variant="caption" color="textMuted">
              {signal.horizon} günlük ufukta {up ? 'yükseliş' : 'düşüş'} yönlü model sinyali
            </AppText>
          </View>
          <View style={styles.right}>
            <AppText variant="number" style={{ color: p.text, fontSize: 18 }}>
              {signal.confidence}
            </AppText>
            <AppText variant="caption" color="textFaint">
              güven
            </AppText>
          </View>
          <Ionicons name="chevron-forward" size={16} color={p.textFaint} />
        </View>
        <View style={styles.badges}>
          <Badge label={up ? 'Alım yönlü' : 'Satış yönlü'} tone={up ? 'up' : 'down'} />
          <Badge label={`${signal.horizon} gün`} />
        </View>
      </GlassCard>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  flex: { flex: 1, gap: 2 },
  right: { alignItems: 'flex-end' },
  badges: { flexDirection: 'row', gap: 6, marginTop: 10, marginLeft: 54 },
});
