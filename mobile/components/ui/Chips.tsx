// Küçük cam çip seçici (1A/3A/1Y/5Y, 1/5/20 gün, filtreler...)
import * as Haptics from 'expo-haptics';
import { Pressable, StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';

import { radius } from '@/theme/colors';
import { useTheme } from '@/theme/ThemeProvider';
import { AppText } from './AppText';

interface Props<T extends string | number> {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  style?: StyleProp<ViewStyle>;
  accessibilityLabel?: string;
}

export function Chips<T extends string | number>({ value, options, onChange, style, accessibilityLabel }: Props<T>) {
  const p = useTheme();
  return (
    <View style={[styles.row, style]} accessibilityRole="tablist" accessibilityLabel={accessibilityLabel}>
      {options.map((o) => {
        const active = o.value === value;
        return (
          <Pressable
            key={String(o.value)}
            accessibilityRole="tab"
            accessibilityState={{ selected: active }}
            hitSlop={4}
            onPress={() => {
              if (active) return;
              Haptics.selectionAsync().catch(() => {});
              onChange(o.value);
            }}
            style={[
              styles.chip,
              active
                ? { backgroundColor: p.accentSoft, borderColor: p.accent }
                : { backgroundColor: p.inputFill, borderColor: p.glassBorder },
            ]}
          >
            <AppText variant="caption" style={{ color: active ? p.accent : p.textMuted }}>
              {o.label}
            </AppText>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', gap: 6, flexWrap: 'wrap' },
  chip: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: radius.pill,
    borderWidth: StyleSheet.hairlineWidth * 2,
  },
});
