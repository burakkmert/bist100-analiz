// Yüzen yapay zekâ balonu: sıvı cam küre, içinde dönen renk halkası ve nefes alan ışıma.
// • Dokun → o anki ekranın görüntüsü alınır ve asistan açılır (görüntüyü eklemek kullanıcıya kalmış).
// • Sürükle → ekranın sağ ya da sol kenarına yapışır.
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { LinearGradient } from 'expo-linear-gradient';
import { router, usePathname } from 'expo-router';
import { useEffect } from 'react';
import { StyleSheet, useWindowDimensions, View } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, {
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withSequence,
  withSpring,
  withTiming,
} from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { captureScreen } from 'react-native-view-shot';
import Svg, { Circle, Defs, RadialGradient, Stop } from 'react-native-svg';

import { useAssistant, type ScreenContext } from '@/store/assistant';
import { useTheme } from '@/theme/ThemeProvider';

/** Yol → ekran bağlamı (POST /ai/chat'teki context alanı) */
function contextFromPath(path: string): ScreenContext {
  const asset = path.match(/^\/asset\/([^/]+)/);
  if (asset) return { screen: 'asset_detail', code: decodeURIComponent(asset[1]).toUpperCase() };
  if (path.startsWith('/markets')) return { screen: 'markets' };
  if (path.startsWith('/portfolio')) return { screen: 'portfolio' };
  if (path.startsWith('/settings')) return { screen: 'settings' };
  return { screen: 'home' };
}

const SIZE = 54;
/** Boştayken balon yarı saydam; dokunurken/sürüklerken netleşir */
const IDLE_OPACITY = 0.62;
const MARGIN = 16;
const TAB_BAR_ZONE = 110; // sekme çubuğunun üstünde kalsın

export function AIBubble() {
  const p = useTheme();
  const insets = useSafeAreaInsets();
  const { width, height } = useWindowDimensions();
  const setLastScreen = useAssistant((s) => s.setLastScreen);
  const setContext = useAssistant((s) => s.setContext);
  const pathname = usePathname();

  const minY = insets.top + MARGIN;
  const maxY = height - insets.bottom - TAB_BAR_ZONE - SIZE - MARGIN;
  const rightX = width - SIZE - MARGIN;

  // Konum
  const x = useSharedValue(rightX);
  const y = useSharedValue(maxY - 10);
  const startX = useSharedValue(0);
  const startY = useSharedValue(0);
  const pressed = useSharedValue(1);
  const active = useSharedValue(0);

  // Süs animasyonları
  const spin = useSharedValue(0);
  const breathe = useSharedValue(0);
  useEffect(() => {
    spin.value = withRepeat(withTiming(1, { duration: 6000, easing: Easing.linear }), -1, false);
    breathe.value = withRepeat(
      withSequence(
        withTiming(1, { duration: 1800, easing: Easing.inOut(Easing.sin) }),
        withTiming(0, { duration: 1800, easing: Easing.inOut(Easing.sin) }),
      ),
      -1,
      false,
    );
  }, [spin, breathe]);

  async function open() {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    try {
      // Kullanıcının baktığı ekranın görüntüsü (asistanda "Az önceki ekran" olarak eklenebilir)
      const uri = await captureScreen({ format: 'jpg', quality: 0.6, result: 'data-uri' });
      setLastScreen(uri);
    } catch {
      setLastScreen(null);
    }
    setContext(contextFromPath(pathname));
    router.push('/assistant');
  }

  const pan = Gesture.Pan()
    .minDistance(6)
    .onBegin(() => {
      startX.value = x.value;
      startY.value = y.value;
      pressed.value = withSpring(1.06);
      active.value = withTiming(1, { duration: 150 });
    })
    .onChange((e) => {
      x.value = startX.value + e.translationX;
      y.value = Math.min(maxY, Math.max(minY, startY.value + e.translationY));
    })
    .onFinalize((e) => {
      pressed.value = withSpring(1);
      active.value = withTiming(0, { duration: 400 });
      // En yakın kenara yapış (fırlatma hızını da hesaba kat)
      const projected = x.value + e.velocityX * 0.15;
      x.value = withSpring(projected + SIZE / 2 < width / 2 ? MARGIN : rightX, { damping: 18, stiffness: 160 });
    });

  const tap = Gesture.Tap()
    .runOnJS(true)
    .onBegin(() => {
      pressed.value = withSpring(0.92);
      active.value = withTiming(1, { duration: 120 });
    })
    .onFinalize(() => {
      pressed.value = withSpring(1);
      active.value = withTiming(0, { duration: 400 });
    })
    .onEnd(() => {
      open();
    });

  const gesture = Gesture.Exclusive(pan, tap);

  const pos = useAnimatedStyle(() => ({
    opacity: IDLE_OPACITY + active.value * (1 - IDLE_OPACITY),
    transform: [{ translateX: x.value }, { translateY: y.value }, { scale: pressed.value }],
  }));
  const ring = useAnimatedStyle(() => ({ transform: [{ rotate: `${spin.value * 360}deg` }] }));
  const glow = useAnimatedStyle(() => ({
    opacity: 0.25 + breathe.value * 0.3,
    transform: [{ scale: 0.9 + breathe.value * 0.1 }],
  }));

  const isDark = p.name === 'dark';

  return (
    <GestureDetector gesture={gesture}>
      <Animated.View
        style={[styles.wrap, pos]}
        accessibilityRole="button"
        accessibilityLabel="Yapay zekâ asistanını aç"
        accessibilityHint="Ekrandaki şeyler hakkında soru sorabilir, grafik ya da görsel gönderebilirsiniz"
      >
        {/* Dış ışıma */}
        <Animated.View style={[styles.glow, glow]} pointerEvents="none">
          <Svg width={SIZE * 2} height={SIZE * 2}>
            <Defs>
              <RadialGradient id="ai-glow" cx="50%" cy="50%" r="50%">
                <Stop offset="0.35" stopColor={p.accent} stopOpacity={isDark ? 0.35 : 0.18} />
                <Stop offset="1" stopColor={p.accent} stopOpacity={0} />
              </RadialGradient>
            </Defs>
            <Circle cx={SIZE} cy={SIZE} r={SIZE} fill="url(#ai-glow)" />
          </Svg>
        </Animated.View>

        <View style={styles.orb}>
          {/* Dönen renk halkası (küreye "sıvı" hareket verir) */}
          <Animated.View style={[styles.ringBox, ring]}>
            <LinearGradient
              colors={
                isDark
                  ? ['rgba(110,168,255,0.7)', 'rgba(167,139,250,0.5)', 'rgba(56,217,196,0.5)', 'rgba(110,168,255,0.7)']
                  : ['rgba(47,111,237,0.45)', 'rgba(140,150,170,0.35)', 'rgba(47,111,237,0.45)', 'rgba(140,150,170,0.35)']
              }
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 1 }}
              style={StyleSheet.absoluteFill}
            />
          </Animated.View>

          {/* Cam çekirdek */}
          <View
            style={[
              styles.core,
              { backgroundColor: isDark ? 'rgba(20,30,55,0.55)' : 'rgba(255,255,255,0.55)' },
            ]}
          >
            <LinearGradient
              colors={[isDark ? 'rgba(255,255,255,0.35)' : 'rgba(255,255,255,0.95)', 'rgba(255,255,255,0)']}
              end={{ x: 0.5, y: 0.6 }}
              style={styles.gloss}
            />
            <Ionicons name="sparkles-outline" size={21} color={isDark ? 'rgba(207,224,255,0.9)' : 'rgba(14,21,38,0.6)'} />
          </View>
        </View>
      </Animated.View>
    </GestureDetector>
  );
}

const RING = 3;

const styles = StyleSheet.create({
  wrap: { position: 'absolute', left: 0, top: 0, width: SIZE, height: SIZE, zIndex: 50 },
  glow: { position: 'absolute', left: -SIZE / 2, top: -SIZE / 2 },
  orb: {
    width: SIZE,
    height: SIZE,
    borderRadius: SIZE / 2,
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000',
    shadowOpacity: 0.15,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 6 },
  },
  ringBox: { position: 'absolute', width: SIZE * 1.5, height: SIZE * 1.5 },
  core: {
    width: SIZE - RING * 2,
    height: SIZE - RING * 2,
    borderRadius: (SIZE - RING * 2) / 2,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  gloss: { position: 'absolute', top: 0, left: 0, right: 0, height: '60%' },
});
