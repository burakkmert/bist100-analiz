// Küçük durum rozeti (risk seviyesi, yön, rejim...).
import { StyleSheet, View } from 'react-native';

import { radius } from '@/theme/colors';
import { useTheme } from '@/theme/ThemeProvider';
import { AppText } from './AppText';
import { withAlpha, type Tone } from './GlassIcon';

export function Badge({ label, tone = 'neutral' }: { label: string; tone?: Tone }) {
  const p = useTheme();
  const c = tone === 'neutral' ? p.textMuted : p[tone];
  const bg = tone === 'neutral' ? p.glassFillStrong : withAlpha(c, 0.15);
  return (
    <View style={[styles.badge, { backgroundColor: bg, borderColor: withAlpha(c, 0.3) }]}>
      <AppText variant="caption" style={{ color: c }}>
        {label}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    alignSelf: 'flex-start',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radius.pill,
    borderWidth: StyleSheet.hairlineWidth * 2,
  },
});
