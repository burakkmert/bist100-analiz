// Giriş ekranlarının ortak çerçevesi: logo, başlık, cam kart.
import type { ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';

import { AppText, GlassCard, GlassIcon, Screen } from '@/components/ui';

interface Props {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}

export function AuthShell({ title, subtitle, children, footer }: Props) {
  return (
    <Screen contentStyle={styles.content}>
      <Animated.View entering={FadeInDown.duration(500)} style={styles.header}>
        <GlassIcon name="pulse" size={64} />
        <AppText variant="display" style={styles.center}>
          {title}
        </AppText>
        {subtitle ? (
          <AppText color="textMuted" style={styles.center}>
            {subtitle}
          </AppText>
        ) : null}
      </Animated.View>

      <Animated.View entering={FadeInDown.delay(120).duration(500)}>
        <GlassCard padding={20}>
          <View style={styles.form}>{children}</View>
        </GlassCard>
      </Animated.View>

      {footer ? <Animated.View entering={FadeInDown.delay(220).duration(500)}>{footer}</Animated.View> : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { flexGrow: 1, justifyContent: 'center', gap: 24 },
  header: { alignItems: 'center', gap: 10 },
  center: { textAlign: 'center' },
  form: { gap: 14 },
});
