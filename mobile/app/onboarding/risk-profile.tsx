// 3 soruluk risk profili anketi → PUT /me/profile
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import Animated, { FadeIn, FadeInDown } from 'react-native-reanimated';

import { patchProfile } from '@/api/profile';
import { AppText, Badge, Button, GlassCard, GlassIcon, Screen, TextField, type IconName } from '@/components/ui';
import { useSettings, type RiskProfile } from '@/store/settings';
import { radius } from '@/theme/colors';
import { useTheme } from '@/theme/ThemeProvider';

interface Question {
  q: string;
  options: { label: string; score: number }[];
}

const QUESTIONS: Question[] = [
  {
    q: 'Yatırımınız bir ayda %15 değer kaybetse ne yaparsınız?',
    options: [
      { label: 'Endişelenir, pozisyonu kapatmayı düşünürüm', score: 0 },
      { label: 'Bekler, durumu izlerim', score: 1 },
      { label: 'Fırsat olarak görür, ekleme yapmayı düşünürüm', score: 2 },
    ],
  },
  {
    q: 'Yatırımlarınızı genellikle ne kadar süre tutarsınız?',
    options: [
      { label: 'Birkaç gün – birkaç hafta', score: 2 },
      { label: 'Birkaç ay', score: 1 },
      { label: 'Bir yıldan uzun', score: 0 },
    ],
  },
  {
    q: 'Sizin için hangisi daha önemli?',
    options: [
      { label: 'Anaparamı korumak', score: 0 },
      { label: 'Dengeli büyüme', score: 1 },
      { label: 'Yüksek getiri potansiyeli, dalgalanmaya razıyım', score: 2 },
    ],
  },
];

const PROFILES: Record<RiskProfile, { title: string; text: string; icon: IconName; tone: 'up' | 'accent' | 'warn' }> = {
  cautious: {
    title: 'Temkinli',
    text: 'Yalnızca yüksek güvenli model sinyalleri gösterilir (güven ≥ 75). Önerilen pozisyon büyüklüğü bütçenin %5\'i.',
    icon: 'leaf-outline',
    tone: 'up',
  },
  balanced: {
    title: 'Dengeli',
    text: 'Orta ve yüksek güvenli sinyaller gösterilir (güven ≥ 65). Önerilen pozisyon büyüklüğü bütçenin %10\'u.',
    icon: 'scale-outline',
    tone: 'accent',
  },
  aggressive: {
    title: 'Atak',
    text: 'Daha fazla sinyal gösterilir (güven ≥ 55), dalgalanma daha yüksektir. Önerilen pozisyon büyüklüğü bütçenin %15\'i.',
    icon: 'flash-outline',
    tone: 'warn',
  },
};

function scoreToProfile(total: number): RiskProfile {
  if (total <= 2) return 'cautious';
  if (total <= 4) return 'balanced';
  return 'aggressive';
}

export default function RiskProfileScreen() {
  const p = useTheme();
  const save = useSettings((s) => s.setRiskProfile);
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<number[]>([]);
  const [budget, setBudget] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const done = step >= QUESTIONS.length;
  const profile = done ? scoreToProfile(answers.reduce((a, b) => a + b, 0)) : null;

  function choose(score: number) {
    Haptics.selectionAsync().catch(() => {});
    setAnswers((a) => [...a.slice(0, step), score]);
    setStep((s) => s + 1);
  }

  async function finish() {
    if (!profile) return;
    const parsed = budget ? Number(budget.replace(/\./g, '').replace(',', '.')) : null;
    if (parsed !== null && (!Number.isFinite(parsed) || parsed < 0)) return setError('Geçerli bir tutar girin.');
    setBusy(true);
    setError(null);
    try {
      await patchProfile({ risk_profile: profile, budget: parsed });
      save(profile, parsed); // kök düzendeki koruma ana sayfaya yönlendirir
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Kaydedilemedi.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen>
      <Animated.View entering={FadeIn.duration(300)} style={styles.header}>
        <AppText variant="caption" color="accent">
          ADIM 2 / 2 · RİSK PROFİLİ
        </AppText>
        <AppText variant="title">{done ? 'Profiliniz hazır' : 'Sizi biraz tanıyalım'}</AppText>
        {/* İlerleme çubukları */}
        <View style={styles.progress}>
          {QUESTIONS.map((_, i) => (
            <View
              key={i}
              style={[styles.dot, { backgroundColor: i < step ? p.accent : i === step ? p.accentSoft : p.separator }]}
            />
          ))}
        </View>
      </Animated.View>

      {!done ? (
        <Animated.View key={step} entering={FadeInDown.duration(320)} style={styles.gap}>
          <AppText variant="heading" style={styles.question}>
            {QUESTIONS[step].q}
          </AppText>
          {QUESTIONS[step].options.map((o) => {
            const selected = answers[step] === o.score;
            return (
              <Pressable key={o.label} onPress={() => choose(o.score)} accessibilityRole="button">
                <GlassCard style={selected ? { borderRadius: radius.lg, borderWidth: 1.5, borderColor: p.accent } : undefined}>
                  <View style={styles.option}>
                    <AppText variant="bodyMedium" style={styles.flex}>
                      {o.label}
                    </AppText>
                    <Ionicons name="chevron-forward" size={18} color={p.textFaint} />
                  </View>
                </GlassCard>
              </Pressable>
            );
          })}
          {step > 0 ? <Button variant="ghost" title="Geri" icon="arrow-back" onPress={() => setStep((s) => s - 1)} /> : null}
        </Animated.View>
      ) : profile ? (
        <Animated.View entering={FadeIn.duration(400)} style={styles.gap}>
          <GlassCard padding={20}>
            <View style={styles.result}>
              <GlassIcon name={PROFILES[profile].icon} tone={PROFILES[profile].tone} size={56} />
              <Badge label={PROFILES[profile].title.toUpperCase()} tone={PROFILES[profile].tone} />
              <AppText color="textMuted" style={styles.centerText}>
                {PROFILES[profile].text}
              </AppText>
            </View>
          </GlassCard>

          <TextField
            label="Yatırım bütçesi (isteğe bağlı, ₺)"
            icon="wallet-outline"
            placeholder="ör. 50000"
            keyboardType="numeric"
            value={budget}
            onChangeText={setBudget}
            error={error}
          />
          <AppText variant="caption" color="textFaint">
            Bütçe yalnızca önerilen adet hesabında kullanılır. Profilinizi daha sonra Ayarlar'dan değiştirebilirsiniz.
          </AppText>

          <Button title="Kaydet ve başla" onPress={finish} loading={busy} />
          <Button
            variant="ghost"
            title="Anketi yeniden yap"
            onPress={() => {
              setAnswers([]);
              setStep(0);
            }}
          />
        </Animated.View>
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: { gap: 8 },
  progress: { flexDirection: 'row', gap: 6, marginTop: 6 },
  dot: { flex: 1, height: 4, borderRadius: 2 },
  gap: { gap: 12 },
  question: { marginBottom: 4 },
  option: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  flex: { flex: 1 },
  result: { alignItems: 'center', gap: 12 },
  centerText: { textAlign: 'center' },
});
