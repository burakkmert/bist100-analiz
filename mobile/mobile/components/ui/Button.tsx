// Butonlar: "primary" (dolu, gradyanlı), "glass" (cam), "ghost" (yalnızca metin).
// Basınca hafifçe küçülür ve dokunsal geri bildirim verir.
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { LinearGradient } from 'expo-linear-gradient';
import type { ReactNode } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withSpring } from 'react-native-reanimated';

import { radius } from '@/theme/colors';
import { useTheme } from '@/theme/ThemeProvider';
import { AppText } from './AppText';
import { GlassCard } from './GlassCard';
import type { IconName } from './GlassIcon';

interface Props {
  title: string;
  onPress?: () => void;
  variant?: 'primary' | 'glass' | 'ghost';
  icon?: IconName;
  /** İkon yerine özel öğe (ör. marka logosu) */
  leading?: ReactNode;
  loading?: boolean;
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
}

const AnimatedPressable = Animated.createAnimatedComponent(Pressable);

export function Button({ title, onPress, variant = 'primary', icon, leading, loading, disabled, style }: Props) {
  const p = useTheme();
  const scale = useSharedValue(1);
  const pressStyle = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }] }));
  const inactive = disabled || loading;

  const fg = variant === 'primary' ? p.onAccent : variant === 'ghost' ? p.accent : p.text;

  const content = (
    <View style={styles.row}>
      {loading ? (
        <ActivityIndicator color={fg} />
      ) : (
        <>
          {leading}
          {icon ? <Ionicons name={icon} size={19} color={fg} /> : null}
          <AppText variant="bodyMedium" style={{ color: fg, fontFamily: 'Inter_600SemiBold' }}>
            {title}
          </AppText>
        </>
      )}
    </View>
  );

  return (
    <AnimatedPressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!inactive, busy: !!loading }}
      disabled={inactive}
      onPressIn={() => (scale.value = withSpring(0.97, { damping: 18, stiffness: 400 }))}
      onPressOut={() => (scale.value = withSpring(1, { damping: 14, stiffness: 300 }))}
      onPress={() => {
        Haptics.selectionAsync().catch(() => {});
        onPress?.();
      }}
      style={[{ opacity: disabled ? 0.5 : 1 }, pressStyle, style]}
    >
      {variant === 'primary' ? (
        <View style={styles.primary}>
          <LinearGradient
            colors={p.name === 'dark' ? ['#8EBBFF', '#5A8DFF'] : ['#4A84FF', '#2459D6']}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={StyleSheet.absoluteFill}
          />
          <LinearGradient
            colors={['rgba(255,255,255,0.45)', 'rgba(255,255,255,0)']}
            end={{ x: 0, y: 0.55 }}
            style={StyleSheet.absoluteFill}
          />
          {content}
        </View>
      ) : variant === 'glass' ? (
        <GlassCard radius={radius.pill} padding={0}>
          <View style={styles.inner}>{content}</View>
        </GlassCard>
      ) : (
        <View style={styles.inner}>{content}</View>
      )}
    </AnimatedPressable>
  );
}

const styles = StyleSheet.create({
  primary: {
    borderRadius: radius.pill,
    overflow: 'hidden',
    minHeight: 52,
    justifyContent: 'center',
    paddingHorizontal: 20,
  },
  inner: { minHeight: 52, justifyContent: 'center', paddingHorizontal: 20 },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10 },
});
