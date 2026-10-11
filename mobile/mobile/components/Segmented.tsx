// Cam görünümlü bölümlü seçici (Hisse/Fon, Sistem/Açık/Koyu...)
import * as Haptics from 'expo-haptics';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/ui';
import { radius } from '@/theme/colors';
import { useTheme } from '@/theme/ThemeProvider';

interface Props<T extends string> {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
}

export function Segmented<T extends string>({ value, options, onChange }: Props<T>) {
  const p = useTheme();
  return (
    <View style={[styles.wrap, { backgroundColor: p.inputFill, borderColor: p.glassBorder }]} accessibilityRole="tablist">
      {options.map((o) => {
        const active = o.value === value;
        return (
          <Pressable
            key={o.value}
            accessibilityRole="tab"
            accessibilityState={{ selected: active }}
            onPress={() => {
              if (!active) Haptics.selectionAsync().catch(() => {});
              onChange(o.value);
            }}
            style={[styles.item, active && { backgroundColor: p.glassFillStrong, borderColor: p.glassBorder }]}
          >
            <AppText variant="bodyMedium" style={{ color: active ? p.text : p.textMuted }}>
              {o.label}
            </AppText>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flexDirection: 'row', padding: 4, borderRadius: radius.pill, borderWidth: StyleSheet.hairlineWidth * 2 },
  item: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: 9,
    borderRadius: radius.pill,
    borderWidth: StyleSheet.hairlineWidth * 2,
    borderColor: 'transparent',
  },
});
