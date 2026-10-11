// Tema değişince eski ekranın görüntüsünü en üstte gösterip yavaşça eritir.
import { useEffect, useRef } from 'react';
import { Image, StyleSheet } from 'react-native';
import Animated, { Easing, useAnimatedStyle, useSharedValue, withTiming } from 'react-native-reanimated';

import { useThemeFade } from '@/store/themeFade';
import { useTheme } from '@/theme/ThemeProvider';

const FADE_MS = 380;

export function ThemeFadeOverlay() {
  const snapshot = useThemeFade((s) => s.snapshot);
  if (!snapshot) return null;
  return <Fader key={snapshot} uri={snapshot} />;
}

function Fader({ uri }: { uri: string }) {
  const p = useTheme();
  const startTheme = useRef(p.name);
  const fired = useRef(false);
  const opacity = useSharedValue(1);
  const clear = useThemeFade((s) => s.clear);

  // Görüntü ekrana oturunca temayı değiştir (yalnızca bir kez)
  const fire = () => {
    if (fired.current) return;
    fired.current = true;
    const cb = useThemeFade.getState().onShown;
    requestAnimationFrame(() => cb?.());
  };

  // Görüntü yüklenme olayı gelmezse bile en geç 120 ms'de devam et
  useEffect(() => {
    const t = setTimeout(fire, 120);
    const safety = setTimeout(clear, 2500); // hiçbir koşulda ekranda takılı kalmasın
    return () => {
      clearTimeout(t);
      clearTimeout(safety);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Yeni tema çizildiğinde erimeye başla
  useEffect(() => {
    if (p.name === startTheme.current) return;
    const raf = requestAnimationFrame(() => {
      opacity.value = withTiming(0, { duration: FADE_MS, easing: Easing.inOut(Easing.quad) });
    });
    const t = setTimeout(clear, FADE_MS + 60);
    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(t);
    };
  }, [p.name, opacity, clear]);

  const style = useAnimatedStyle(() => ({ opacity: opacity.value }));

  return (
    <Animated.View style={[StyleSheet.absoluteFill, styles.top, style]} pointerEvents="none">
      <Image source={{ uri }} style={StyleSheet.absoluteFill} resizeMode="cover" fadeDuration={0} onLoad={fire} />
    </Animated.View>
  );
}

const styles = StyleSheet.create({ top: { zIndex: 999, elevation: 999 } });
