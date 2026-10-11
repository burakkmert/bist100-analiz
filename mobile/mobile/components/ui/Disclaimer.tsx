// Her sinyal ve tahmin ekranında görünmesi zorunlu kısa uyarı şeridi.
import { Ionicons } from '@expo/vector-icons';
import { StyleSheet, View } from 'react-native';

import { DISCLAIMER_SHORT } from '@/lib/legal';
import { radius } from '@/theme/colors';
import { useTheme } from '@/theme/ThemeProvider';
import { AppText } from './AppText';
import { withAlpha } from './GlassIcon';

export function Disclaimer() {
  const p = useTheme();
  return (
    <View
      accessibilityRole="text"
      style={[styles.box, { backgroundColor: withAlpha(p.warn, 0.1), borderColor: withAlpha(p.warn, 0.28) }]}
    >
      <Ionicons name="information-circle-outline" size={16} color={p.warn} />
      <AppText variant="caption" color="textMuted" style={styles.text}>
        {DISCLAIMER_SHORT}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  box: {
    flexDirection: 'row',
    gap: 8,
    alignItems: 'flex-start',
    padding: 10,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth * 2,
  },
  text: { flex: 1, lineHeight: 17 },
});
