// "Liquid glass" yüzey: bulanık cam + üst kenarda ışık yansıması + ince parlak çerçeve.
//
// Not (pil): iOS'ta sistem bulanıklığı (UIVisualEffectView) donanımda verimli çalışır.
// Android'de canlı bulanıklık, arkadaki hareketli zemin her karede değiştiği için sürekli
// yeniden hesaplanır ve pil yer. Bu yüzden Android'de bulanıklık yerine yarı saydam dolgu
// + aynı ışık yansıması kullanılır; görünüm çok yakındır.
import { BlurView } from 'expo-blur';
import { LinearGradient } from 'expo-linear-gradient';
import type { ReactNode } from 'react';
import { Platform, StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';

import { radius as R } from '@/theme/colors';
import { useTheme } from '@/theme/ThemeProvider';

interface Props {
  children?: ReactNode;
  style?: StyleProp<ViewStyle>;
  /** Kartın iç boşluğu */
  padding?: number;
  radius?: number;
  /** Daha opak yüzey (ör. sekme çubuğu, alt panel) */
  strong?: boolean;
  intensity?: number;
}

const USE_LIVE_BLUR = Platform.OS === 'ios';

export function GlassCard({ children, style, padding = 16, radius = R.lg, strong, intensity = 40 }: Props) {
  const p = useTheme();

  return (
    <View
      style={[
        styles.shadow,
        {
          borderRadius: radius,
          shadowColor: p.glassShadow,
          // Açık temada gölge yarı saydam camın içinden görünüp yazıların arkasını kirli/koyu gösteriyordu.
          shadowOpacity: p.name === 'dark' ? 0.35 : 0,
        },
        style,
      ]}
    >
      <View style={[styles.clip, { borderRadius: radius }]}>
        {USE_LIVE_BLUR ? (
          <BlurView tint={p.name === 'dark' ? 'dark' : 'extraLight'} intensity={intensity} style={StyleSheet.absoluteFill} />
        ) : null}

        {/* Cam dolgusu */}
        <View
          style={[
            StyleSheet.absoluteFill,
            {
              backgroundColor: USE_LIVE_BLUR
                ? strong
                  ? p.glassFillStrong
                  : p.glassFill
                : p.name === 'dark'
                  ? strong
                    ? 'rgba(30,40,62,0.88)'
                    : 'rgba(28,38,60,0.62)'
                  : strong
                    ? 'rgba(255,255,255,0.92)'
                    : 'rgba(255,255,255,0.74)',
            },
          ]}
        />

        {/* Işık yansıması: üstten aşağı sönen parlaklık — "sıvı cam" hissini veren kısım */}
        <LinearGradient
          colors={[p.glassHighlight, 'rgba(255,255,255,0)']}
          start={{ x: 0, y: 0 }}
          end={{ x: 0, y: 0.6 }}
          style={[StyleSheet.absoluteFill, { opacity: p.name === 'dark' ? 0.18 : 0.55 }]}
          pointerEvents="none"
        />

        <View style={{ padding }}>{children}</View>

        {/* İnce çerçeve (en üstte, içeriği örtmez) */}
        <View
          pointerEvents="none"
          style={[
            StyleSheet.absoluteFill,
            { borderRadius: radius, borderWidth: StyleSheet.hairlineWidth * 2, borderColor: p.glassBorder },
          ]}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  shadow: {
    shadowOffset: { width: 0, height: 10 },
    shadowRadius: 24,
    elevation: 0, // Android gölgesi yarı saydam yüzeyde gri leke bırakır; kapalı
  },
  clip: { overflow: 'hidden' },
});
