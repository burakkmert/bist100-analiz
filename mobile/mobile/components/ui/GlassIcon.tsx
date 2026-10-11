// Cam damla görünümlü ikon: renkli iç ışıma + üstte parlak yansıma + ince çerçeve.
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import type { ComponentProps } from 'react';
import { StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';

import { useTheme } from '@/theme/ThemeProvider';

export type IconName = ComponentProps<typeof Ionicons>['name'];
export type Tone = 'accent' | 'up' | 'down' | 'warn' | 'neutral';

interface Props {
  name: IconName;
  size?: number; // dış kutunun boyu
  tone?: Tone;
  style?: StyleProp<ViewStyle>;
}

export function GlassIcon({ name, size = 44, tone = 'accent', style }: Props) {
  const p = useTheme();
  const color = tone === 'neutral' ? p.text : p[tone];
  const isDark = p.name === 'dark';
  const r = size * 0.32; // yumuşak kare (squircle'a yakın)

  return (
    <View style={[{ width: size, height: size, borderRadius: r }, styles.wrap, style]}>
      {/* Renkli iç ışıma */}
      <LinearGradient
        colors={[withAlpha(color, isDark ? 0.42 : 0.3), withAlpha(color, isDark ? 0.1 : 0.08)]}
        start={{ x: 0.2, y: 0 }}
        end={{ x: 0.8, y: 1 }}
        style={StyleSheet.absoluteFill}
      />
      {/* Cam dolgu */}
      <View
        style={[StyleSheet.absoluteFill, { backgroundColor: isDark ? 'rgba(255,255,255,0.05)' : 'rgba(255,255,255,0.45)' }]}
      />
      {/* Üst parlama: yarım elips */}
      <LinearGradient
        colors={[isDark ? 'rgba(255,255,255,0.35)' : 'rgba(255,255,255,0.95)', 'rgba(255,255,255,0)']}
        style={[styles.gloss, { height: size * 0.5, borderTopLeftRadius: r, borderTopRightRadius: r }]}
      />
      <Ionicons name={name} size={size * 0.48} color={color} />
      <View
        pointerEvents="none"
        style={[
          StyleSheet.absoluteFill,
          { borderRadius: r, borderWidth: 1, borderColor: isDark ? 'rgba(255,255,255,0.16)' : 'rgba(255,255,255,0.9)' },
        ]}
      />
    </View>
  );
}

/** #RRGGBB rengine saydamlık ekler */
export function withAlpha(hex: string, alpha: number) {
  if (!hex.startsWith('#') || hex.length !== 7) return hex;
  const a = Math.round(Math.min(1, Math.max(0, alpha)) * 255)
    .toString(16)
    .padStart(2, '0');
  return `${hex}${a}`;
}

const styles = StyleSheet.create({
  wrap: { overflow: 'hidden', alignItems: 'center', justifyContent: 'center' },
  gloss: { position: 'absolute', top: 0, left: 0, right: 0 },
});
