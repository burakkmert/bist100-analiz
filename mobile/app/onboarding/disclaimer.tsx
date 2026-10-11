// İlk açılış: yasal uyarı. Onay kutusu işaretlenmeden devam edilemez.
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';

import { AppText, Button, GlassCard, GlassIcon, Screen } from '@/components/ui';
import { DISCLAIMER_FULL, DISCLAIMER_VERSION } from '@/lib/legal';
import { useSettings } from '@/store/settings';
import { useTheme } from '@/theme/ThemeProvider';

const ICONS = ['shield-checkmark-outline', 'stats-chart-outline', 'hand-left-outline', 'sparkles-outline'] as const;

export default function DisclaimerScreen() {
  const p = useTheme();
  const accept = useSettings((s) => s.acceptDisclaimer);
  const [checked, setChecked] = useState(false);

  return (
    <Screen>
      <Animated.View entering={FadeInDown.duration(450)} style={styles.header}>
        <AppText variant="caption" color="accent">
          ADIM 1 / 2
        </AppText>
        <AppText variant="title">Başlamadan önce</AppText>
        <AppText color="textMuted">Lütfen aşağıdaki açıklamaları okuyun.</AppText>
      </Animated.View>

      {DISCLAIMER_FULL.map((item, i) => (
        <Animated.View key={item.title} entering={FadeInDown.delay(80 * (i + 1)).duration(450)}>
          <GlassCard>
            <View style={styles.row}>
              <GlassIcon name={ICONS[i % ICONS.length]} size={40} tone={i === 0 ? 'warn' : 'accent'} />
              <View style={styles.flex}>
                <AppText variant="heading">{item.title}</AppText>
                <AppText color="textMuted" style={styles.body}>
                  {item.body}
                </AppText>
              </View>
            </View>
          </GlassCard>
        </Animated.View>
      ))}

      <Pressable
        accessibilityRole="checkbox"
        accessibilityState={{ checked }}
        onPress={() => {
          Haptics.selectionAsync().catch(() => {});
          setChecked((c) => !c);
        }}
        style={styles.check}
      >
        <View
          style={[
            styles.box,
            { borderColor: checked ? p.accent : p.glassBorder, backgroundColor: checked ? p.accent : p.inputFill },
          ]}
        >
          {checked ? <Ionicons name="checkmark" size={16} color={p.onAccent} /> : null}
        </View>
        <AppText style={styles.flex}>Okudum, anladım. Uygulamanın yatırım tavsiyesi vermediğini kabul ediyorum.</AppText>
      </Pressable>

      <Button title="Devam et" disabled={!checked} onPress={() => accept(DISCLAIMER_VERSION)} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: { gap: 6, marginBottom: 4 },
  row: { flexDirection: 'row', gap: 14, alignItems: 'flex-start' },
  flex: { flex: 1 },
  body: { marginTop: 4 },
  check: { flexDirection: 'row', gap: 12, alignItems: 'center', paddingVertical: 4 },
  box: { width: 24, height: 24, borderRadius: 7, borderWidth: 1.5, alignItems: 'center', justifyContent: 'center' },
});
