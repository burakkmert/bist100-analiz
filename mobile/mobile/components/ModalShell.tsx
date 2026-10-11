// Alttan açılan form ekranlarının ortak çerçevesi: kendi hareketli zemini, başlık + kapat,
// klavyeyle birlikte kayan içerik ve altta sabit eylem alanı.
import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import type { ReactNode } from 'react';
import { Platform, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import Animated, { useAnimatedKeyboard, useAnimatedStyle } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AnimatedBackground } from '@/components/AnimatedBackground';
import { AppText } from '@/components/ui';
import { useTheme } from '@/theme/ThemeProvider';

interface Props {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}

export function ModalShell({ title, subtitle, children, footer }: Props) {
  const p = useTheme();
  const insets = useSafeAreaInsets();
  const keyboard = useAnimatedKeyboard();
  const bottomInset = Math.max(insets.bottom, 12);
  const pad = useAnimatedStyle(() => ({ paddingBottom: keyboard.height.value }));
  const footerPad = useAnimatedStyle(() => ({ paddingBottom: keyboard.height.value > 0 ? 10 : bottomInset }));

  return (
    <View style={styles.flex}>
      <AnimatedBackground />
      <View style={[styles.header, { paddingTop: Platform.OS === 'ios' ? 18 : insets.top + 10 }]}>
        <View style={styles.flex}>
          <AppText variant="title">{title}</AppText>
          {subtitle ? (
            <AppText variant="caption" color="textMuted">
              {subtitle}
            </AppText>
          ) : null}
        </View>
        <Pressable
          onPress={() => router.back()}
          accessibilityLabel="Kapat"
          hitSlop={8}
          style={[styles.close, { backgroundColor: p.glassFillStrong, borderColor: p.glassBorder }]}
        >
          <Ionicons name="close" size={18} color={p.text} />
        </Pressable>
      </View>

      <Animated.View style={[styles.flex, pad]}>
        <ScrollView
          style={styles.flex}
          contentContainerStyle={styles.content}
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode={Platform.OS === 'ios' ? 'interactive' : 'on-drag'}
          alwaysBounceVertical
          showsVerticalScrollIndicator={false}
        >
          {children}
        </ScrollView>
        {footer ? <Animated.View style={[styles.footer, footerPad]}>{footer}</Animated.View> : null}
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  header: { flexDirection: 'row', alignItems: 'flex-start', gap: 12, paddingHorizontal: 20, paddingBottom: 8 },
  close: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: StyleSheet.hairlineWidth * 2,
  },
  content: { paddingHorizontal: 20, paddingTop: 8, paddingBottom: 24, gap: 14 },
  footer: { paddingHorizontal: 20, paddingTop: 10, gap: 8 },
});
