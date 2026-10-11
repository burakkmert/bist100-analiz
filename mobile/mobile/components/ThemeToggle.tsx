// Tema anahtarı — cam yuva + ince çizgi (line-art) güneş/ay ikonları, temanın renklerine uyar.
//
// Takılma neden olurdu, nasıl çözüldü?
//  Tema değişince tüm ekranlar yeniden çizilir. Bu iş topun kayma animasyonuyla aynı anda olursa
//  animasyon kare atlar. Artık önce top kayar (UI iş parçacığında, ~260 ms), animasyon bittiği an
//  tema değişir. Ekranların yeniden çizilmesi animasyonla çakışmaz.
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { LinearGradient } from 'expo-linear-gradient';
import { startTransition, useEffect, useRef } from 'react';
import { Pressable, StyleSheet, useWindowDimensions, View } from 'react-native';
import Animated, {
  Easing,
  interpolate,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';

import { captureScreen } from 'react-native-view-shot';

import { useSettings } from '@/store/settings';
import { useThemeFade } from '@/store/themeFade';
import { useTheme } from '@/theme/ThemeProvider';

const W = 84;
const H = 40;
const PAD = 4;
const KNOB = H - PAD * 2;
const TRAVEL = W - KNOB - PAD * 2;
const DURATION = 200;

export function ThemeToggle() {
  const p = useTheme();
  const setPref = useSettings((s) => s.setThemePreference);
  const startFade = useThemeFade((s) => s.start);
  const isDark = p.name === 'dark';
  const { width } = useWindowDimensions();
  const busy = useRef(false);

  // 0 = açık (top sağda, güneş solda görünür), 1 = koyu (top solda, ay sağda görünür)
  const v = useSharedValue(isDark ? 1 : 0);
  useEffect(() => {
    v.value = isDark ? 1 : 0; // dışarıdan (ör. sistem) değişirse anında eşitle
  }, [isDark, v]);

  const toggle = () => {
    if (busy.current) return;
    busy.current = true;
    Haptics.selectionAsync().catch(() => {});
    const next = isDark ? 0 : 1;
    v.value = withTiming(next, { duration: DURATION, easing: Easing.out(Easing.cubic) });
    setTimeout(async () => {
      const apply = () => {
        startTransition(() => setPref(next ? 'dark' : 'light'));
        busy.current = false;
      };
      try {
        // Top yerine oturduktan sonra ekranın görüntüsünü al; görüntü ekrana konunca tema değişir
        // ve görüntü yavaşça eriyerek yeni temayı ortaya çıkarır.
        // Düşük çözünürlük: görüntü yalnızca ~0,4 sn görünür, böyle çok daha hızlı alınır
        const uri = await captureScreen({ format: 'jpg', quality: 0.7, result: 'tmpfile', width: width * 1.5 });
        startFade(uri, apply);
      } catch {
        apply(); // görüntü alınamazsa doğrudan geçiş
      }
    }, DURATION);
  };

  const knob = useAnimatedStyle(() => ({
    transform: [{ translateX: interpolate(v.value, [0, 1], [TRAVEL, 0]) }],
  }));
  const sun = useAnimatedStyle(() => ({
    opacity: interpolate(v.value, [0, 0.6], [1, 0], 'clamp'),
    transform: [{ rotate: `${v.value * 45}deg` }],
  }));
  const moon = useAnimatedStyle(() => ({
    opacity: interpolate(v.value, [0.4, 1], [0, 1], 'clamp'),
    transform: [{ rotate: `${(v.value - 1) * 40}deg` }],
  }));

  const line = isDark ? 'rgba(225,232,245,0.75)' : 'rgba(14,21,38,0.55)';

  return (
    <Pressable
      onPress={toggle}
      accessibilityRole="switch"
      accessibilityState={{ checked: isDark }}
      accessibilityLabel="Koyu tema"
      hitSlop={8}
    >
      <View
        style={[
          styles.track,
          {
            backgroundColor: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(255,255,255,0.5)',
            borderColor: isDark ? 'rgba(255,255,255,0.16)' : 'rgba(14,21,38,0.1)',
          },
        ]}
      >
        {/* Yuvanın içe gömük hissi: üstte çok hafif koyulaşma */}
        <LinearGradient
          colors={isDark ? ['rgba(0,0,0,0.25)', 'rgba(0,0,0,0)'] : ['rgba(14,21,38,0.06)', 'rgba(14,21,38,0)']}
          end={{ x: 0, y: 0.7 }}
          style={StyleSheet.absoluteFill}
        />

        <Animated.View style={[styles.iconLeft, sun]}>
          <Ionicons name="sunny-outline" size={18} color={line} />
        </Animated.View>
        <Animated.View style={[styles.iconRight, moon]}>
          <Ionicons name="moon-outline" size={16} color={line} />
          <Ionicons name="star-outline" size={8} color={line} style={styles.star} />
        </Animated.View>

        {/* Cam top */}
        <Animated.View
          style={[
            styles.knob,
            {
              backgroundColor: isDark ? 'rgba(255,255,255,0.14)' : 'rgba(255,255,255,0.9)',
              borderColor: isDark ? 'rgba(255,255,255,0.28)' : 'rgba(255,255,255,1)',
              shadowOpacity: isDark ? 0.35 : 0.12,
            },
            knob,
          ]}
        >
          <LinearGradient
            colors={[isDark ? 'rgba(255,255,255,0.35)' : 'rgba(255,255,255,1)', 'rgba(255,255,255,0)']}
            end={{ x: 0.5, y: 0.7 }}
            style={styles.gloss}
          />
        </Animated.View>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  track: {
    width: W,
    height: H,
    borderRadius: H / 2,
    borderWidth: 1,
    padding: PAD,
    justifyContent: 'center',
    overflow: 'hidden',
  },
  iconLeft: { position: 'absolute', left: 13 },
  iconRight: { position: 'absolute', right: 13, flexDirection: 'row' },
  star: { marginLeft: -2, marginTop: -3 },
  knob: {
    width: KNOB,
    height: KNOB,
    borderRadius: KNOB / 2,
    borderWidth: 1,
    overflow: 'hidden',
    shadowColor: '#000',
    shadowRadius: 4,
    shadowOffset: { width: 0, height: 2 },
  },
  gloss: { position: 'absolute', top: 0, left: 0, right: 0, height: '60%' },
});
