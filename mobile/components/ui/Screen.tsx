// Ekran kabı: güvenli alan boşlukları, kaydırma ve klavye kaçınma.
// Arka plan kök düzende bir kez çizilir; ekranlar şeffaftır.
import type { ReactNode } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View, type ViewStyle } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { space } from '@/theme/colors';

interface Props {
  children: ReactNode;
  scroll?: boolean;
  /** Alttaki sekme çubuğu için ek boşluk */
  tabBarSpace?: boolean;
  contentStyle?: ViewStyle;
}

export function Screen({ children, scroll = true, tabBarSpace, contentStyle }: Props) {
  const insets = useSafeAreaInsets();
  const padding: ViewStyle = {
    paddingTop: insets.top + space.lg,
    paddingBottom: insets.bottom + (tabBarSpace ? 110 : space.xl),
    paddingHorizontal: space.lg + 4,
    gap: space.lg,
  };

  return (
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      {scroll ? (
        <ScrollView
          style={styles.flex}
          contentContainerStyle={[padding, contentStyle]}
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode={Platform.OS === 'ios' ? 'interactive' : 'on-drag'}
          showsVerticalScrollIndicator={false}
        >
          {children}
        </ScrollView>
      ) : (
        <View style={[styles.flex, padding, contentStyle]}>{children}</View>
      )}
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({ flex: { flex: 1 } });
