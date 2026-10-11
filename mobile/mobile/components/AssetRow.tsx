// Listelerde tek satır varlık (piyasalar, izleme listesi). Dokununca detaya gider.
import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';

import type { AssetListItem } from '@/api/types';
import { AppText } from '@/components/ui';
import { formatPct, formatPrice } from '@/lib/format';
import { useTheme } from '@/theme/ThemeProvider';

export function AssetRow({ a, first }: { a: AssetListItem; first?: boolean }) {
  const p = useTheme();
  const color = a.change_pct > 0 ? p.up : a.change_pct < 0 ? p.down : p.flat;
  return (
    <Pressable
      onPress={() => router.push(`/asset/${a.code}`)}
      accessibilityRole="button"
      accessibilityLabel={`${a.code}, ${a.name}, ${formatPrice(a.last_price, a.type)}, ${formatPct(a.change_pct)}`}
      style={({ pressed }) => [
        styles.row,
        !first && { borderTopWidth: StyleSheet.hairlineWidth * 2, borderTopColor: p.separator },
        pressed && { backgroundColor: p.glassFill },
      ]}
    >
      <View style={styles.flex}>
        <AppText variant="heading">{a.code}</AppText>
        <AppText variant="caption" color="textMuted" numberOfLines={1}>
          {a.name}
        </AppText>
      </View>
      <View style={styles.right}>
        <AppText variant="number" style={{ color: p.text, fontSize: 15 }}>
          {formatPrice(a.last_price, a.type)}
        </AppText>
        <AppText variant="caption" style={{ color }}>
          {formatPct(a.change_pct)}
        </AppText>
      </View>
      <Ionicons name="chevron-forward" size={16} color={p.textFaint} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 13, gap: 12 },
  flex: { flex: 1, gap: 2 },
  right: { alignItems: 'flex-end', gap: 2 },
});
