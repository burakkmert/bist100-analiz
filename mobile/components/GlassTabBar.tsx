// Yüzen cam sekme çubuğu. Seçili sekmenin arkasında yumuşakça kayan bir ışık kapsülü var.
import { Ionicons } from '@expo/vector-icons';
import type { BottomTabBarProps } from 'expo-router/js-tabs';
import * as Haptics from 'expo-haptics';
import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withSpring } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppText, GlassCard, type IconName } from '@/components/ui';
import { radius } from '@/theme/colors';
import { useTheme } from '@/theme/ThemeProvider';

export const TAB_META: Record<string, { label: string; icon: IconName; iconActive: IconName }> = {
  index: { label: 'Ana sayfa', icon: 'home-outline', iconActive: 'home' },
  markets: { label: 'Piyasalar', icon: 'stats-chart-outline', iconActive: 'stats-chart' },
  portfolio: { label: 'Portföy', icon: 'wallet-outline', iconActive: 'wallet' },
  settings: { label: 'Ayarlar', icon: 'settings-outline', iconActive: 'settings' },
};

const PAD = 6;

export function GlassTabBar({ state, navigation }: BottomTabBarProps) {
  const p = useTheme();
  const insets = useSafeAreaInsets();
  const [width, setWidth] = useState(0);
  const itemW = width > 0 ? width / state.routes.length : 0;

  const x = useSharedValue(0);
  useEffect(() => {
    x.value = withSpring(state.index * itemW, { damping: 20, stiffness: 220, mass: 0.8 });
  }, [state.index, itemW, x]);
  const pill = useAnimatedStyle(() => ({ transform: [{ translateX: x.value }] }));

  return (
    <View style={[styles.wrap, { bottom: Math.max(insets.bottom, 12) }]} pointerEvents="box-none">
      <GlassCard radius={radius.xl} padding={PAD} strong intensity={60}>
        <View style={styles.row} onLayout={(e) => setWidth(e.nativeEvent.layout.width)}>
          {itemW > 0 ? (
            <Animated.View
              style={[
                styles.pill,
                { width: itemW, backgroundColor: p.accentSoft, borderColor: p.glassBorder },
                pill,
              ]}
            />
          ) : null}
          {state.routes.map((route, i) => {
            const focused = state.index === i;
            const meta = TAB_META[route.name] ?? { label: route.name, icon: 'ellipse-outline', iconActive: 'ellipse' };
            const color = focused ? p.accent : p.textMuted;
            return (
              <Pressable
                key={route.key}
                accessibilityRole="tab"
                accessibilityState={{ selected: focused }}
                accessibilityLabel={meta.label}
                style={styles.item}
                onPress={() => {
                  const event = navigation.emit({ type: 'tabPress', target: route.key, canPreventDefault: true });
                  if (!focused && !event.defaultPrevented) {
                    Haptics.selectionAsync().catch(() => {});
                    navigation.navigate(route.name, route.params);
                  }
                }}
              >
                <Ionicons name={focused ? meta.iconActive : meta.icon} size={22} color={color} />
                <AppText variant="caption" style={{ color, fontSize: 11 }}>
                  {meta.label}
                </AppText>
              </Pressable>
            );
          })}
        </View>
      </GlassCard>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { position: 'absolute', left: 16, right: 16 },
  row: { flexDirection: 'row' },
  pill: {
    position: 'absolute',
    top: 0,
    bottom: 0,
    left: 0,
    borderRadius: radius.xl - PAD,
    borderWidth: StyleSheet.hairlineWidth * 2,
  },
  item: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 3, paddingVertical: 8 },
});
