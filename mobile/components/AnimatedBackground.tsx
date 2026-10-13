// Akışkan, sürekli hareket eden arka plan — video yok, tamamen kodla.
//
// Nasıl çalışır?
//  • Tek bir "saat" (0→1, sonsuz döngü) UI iş parçacığında döner.
//  • 5 renkli ışık lekesi bu saatten sinüs/kosinüs ile hesaplanan eğrilerde
//    (sekiz çizer gibi) dolaşır; her lekenin hızı ve fazı farklıdır, bu yüzden
//    renkler sürekli birbirine karışıp ayrılır → "sıvı" görünüm.
//  • Alttaki ana gradyan da çok yavaş döner; renk yönü sürekli değişir.
//  • Döngüdeki katsayılar tam sayı olduğu için döngü başa sarılırken sıçrama olmaz.
//
// Pil: yalnızca transform (konum/ölçek/dönme) değişir; lekeler SVG ile bir kez çizilir,
// her karede yeniden çizilmez, blur filtresi yok. Uygulama arka plandayken saat durur.
import { LinearGradient } from 'expo-linear-gradient';
import { memo, useEffect } from 'react';
import { AppState, StyleSheet, useWindowDimensions, View } from 'react-native';
import Animated, {
  cancelAnimation,
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
  type SharedValue,
} from 'react-native-reanimated';
import Svg, { Circle, Defs, RadialGradient, Stop } from 'react-native-svg';

import { useTheme } from '@/theme/ThemeProvider';

/** Tüm hareketin tek döngüsü (ms). Lekeler bunun 2–5 katı hızla döner → 6–15 sn'lik turlar. */
const CYCLE_MS = 30000;
/** Dönen renk katmanının saydamlığı: düşükse lekeler daha net seçilir */
const SWEEP_OPACITY = 0.32;
const TWO_PI = Math.PI * 2;

/**
 * Her leke: merkez (ekran oranı), yörünge genişliği (ax, ay), hız katsayıları (kx, ky — tam sayı!),
 * faz ve boyut (ekran genişliğine oran).
 */
const ORBITS = [
  { cx: 0.25, cy: 0.2, ax: 0.42, ay: 0.2, kx: 2, ky: 3, phase: 0.0, size: 0.82 },
  { cx: 0.8, cy: 0.22, ax: 0.38, ay: 0.2, kx: 3, ky: 2, phase: 1.7, size: 0.74 },
  { cx: 0.22, cy: 0.8, ax: 0.38, ay: 0.18, kx: 2, ky: 4, phase: 3.1, size: 0.8 },
  { cx: 0.75, cy: 0.82, ax: 0.42, ay: 0.18, kx: 4, ky: 3, phase: 4.4, size: 0.76 },
  { cx: 0.5, cy: 0.5, ax: 0.32, ay: 0.28, kx: 5, ky: 2, phase: 2.3, size: 0.66 },
] as const;

function AnimatedBackgroundBase() {
  const palette = useTheme();
  const { width, height } = useWindowDimensions();
  const clock = useSharedValue(0);

  useEffect(() => {
    const start = () => {
      // Kaldığı yerden devam etsin diye mevcut değerden 1'e, sonra 0→1 sonsuz
      clock.value = withRepeat(withTiming(clock.value + 1, { duration: CYCLE_MS, easing: Easing.linear }), -1, false);
    };
    const stop = () => cancelAnimation(clock);
    start();
    const sub = AppState.addEventListener('change', (s) => (s === 'active' ? start() : stop()));
    return () => {
      sub.remove();
      stop();
    };
  }, [clock]);

  // Ana gradyan: ekranın köşegeninden büyük bir kare, merkez etrafında yavaşça döner
  const diag = Math.ceil(Math.sqrt(width * width + height * height)) + 40;
  const rotateStyle = useAnimatedStyle(() => ({
    transform: [{ rotate: `${clock.value * 360}deg` }],
  }));

  return (
    <View style={[StyleSheet.absoluteFill, styles.clip]} pointerEvents="none">
      {/* 1) Sabit taban: temanın dikey gradyanı */}
      <LinearGradient colors={palette.bgGradient} style={StyleSheet.absoluteFill} />

      {/* 2) Dönen yarı saydam gradyan: renk yönünü sürekli değiştirir */}
      <Animated.View
        style={[
          styles.rotator,
          { width: diag, height: diag, left: (width - diag) / 2, top: (height - diag) / 2, opacity: SWEEP_OPACITY },
          rotateStyle,
        ]}
      >
        <LinearGradient colors={palette.bgSweep} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={StyleSheet.absoluteFill} />
      </Animated.View>

      {/* 3) Akışkan ışık lekeleri */}
      {palette.blobs.map((blob, i) => (
        <Blob
          key={i}
          id={`blob-${palette.name}-${i}`}
          color={blob.color}
          opacity={blob.opacity}
          orbit={ORBITS[i % ORBITS.length]}
          clock={clock}
          width={width}
          height={height}
        />
      ))}

      {/* 4) Hafif üst katman: metnin okunurluğu için kontrastı dengeler */}
      <View style={[StyleSheet.absoluteFill, { backgroundColor: palette.bgVeil }]} />
    </View>
  );
}

interface BlobProps {
  id: string;
  color: string;
  opacity: number;
  orbit: (typeof ORBITS)[number];
  clock: SharedValue<number>;
  width: number;
  height: number;
}

const Blob = memo(function Blob({ id, color, opacity, orbit, clock, width, height }: BlobProps) {
  const size = width * orbit.size;

  const style = useAnimatedStyle(() => {
    const a = clock.value * TWO_PI;
    const x = orbit.cx * width + Math.sin(a * orbit.kx + orbit.phase) * orbit.ax * width;
    const y = orbit.cy * height + Math.cos(a * orbit.ky + orbit.phase) * orbit.ay * height;
    const s = 1 + Math.sin(a * (orbit.kx + orbit.ky) + orbit.phase) * 0.22; // nefes alır gibi büyüyüp küçülür
    return {
      transform: [{ translateX: x - size / 2 }, { translateY: y - size / 2 }, { scale: s }],
    };
  });

  return (
    <Animated.View style={[styles.blob, { width: size, height: size }, style]}>
      <Svg width={size} height={size}>
        <Defs>
          <RadialGradient id={id} cx="50%" cy="50%" r="50%">
            {/* Dolu çekirdek + kısa geçiş: leke "top" gibi seçilir ama kenarı yumuşak kalır */}
            <Stop offset="0" stopColor={color} stopOpacity={opacity} />
            <Stop offset="0.55" stopColor={color} stopOpacity={opacity * 0.85} />
            <Stop offset="0.82" stopColor={color} stopOpacity={opacity * 0.3} />
            <Stop offset="1" stopColor={color} stopOpacity={0} />
          </RadialGradient>
        </Defs>
        <Circle cx={size / 2} cy={size / 2} r={size / 2} fill={`url(#${id})`} />
      </Svg>
    </Animated.View>
  );
});

const styles = StyleSheet.create({
  clip: { overflow: 'hidden' },
  rotator: { position: 'absolute' },
  blob: { position: 'absolute', top: 0, left: 0 },
});

export const AnimatedBackground = memo(AnimatedBackgroundBase);
