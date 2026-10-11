// Yüklenirken görünen yumuşak nabız atan yer tutucu
import { useEffect } from 'react';
import { type DimensionValue } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withRepeat, withTiming } from 'react-native-reanimated';

import { useTheme } from '@/theme/ThemeProvider';

export function Skeleton({ width = '100%', height = 16, radius = 8 }: { width?: DimensionValue; height?: number; radius?: number }) {
  const p = useTheme();
  const v = useSharedValue(0.45);
  useEffect(() => {
    v.value = withRepeat(withTiming(0.9, { duration: 750 }), -1, true);
  }, [v]);
  const style = useAnimatedStyle(() => ({ opacity: v.value }));
  return <Animated.View style={[{ width, height, borderRadius: radius, backgroundColor: p.glassFillStrong }, style]} />;
}
