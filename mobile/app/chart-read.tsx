// Grafik okuma: uygulama içi grafikten ya da galeriden/kameradan gelen görüntüyü yapay zekâya yorumlatır.
// Sonuç: trend, destek/direnç seviyeleri, formasyon, gösterge notu, özet ve yorumun neye dayandığı.
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import * as ImagePicker from 'expo-image-picker';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { Alert, Image, Pressable, StyleSheet, View } from 'react-native';
import Animated, { FadeIn, FadeInDown } from 'react-native-reanimated';

import { readChart, type ChartReading } from '@/api/chartRead';
import { ModalShell } from '@/components/ModalShell';
import { AppText, Badge, Button, Disclaimer, GlassCard, GlassIcon, Skeleton, type IconName, type Tone } from '@/components/ui';
import { formatAxis } from '@/lib/format';
import { useAssistant } from '@/store/assistant';
import { useChartRead } from '@/store/chartRead';
import { radius } from '@/theme/colors';
import { useTheme } from '@/theme/ThemeProvider';

const TREND: Record<ChartReading['trend'], { label: string; tone: Tone; icon: IconName }> = {
  up: { label: 'Yükselen eğilim', tone: 'up', icon: 'trending-up' },
  down: { label: 'Düşen eğilim', tone: 'down', icon: 'trending-down' },
  flat: { label: 'Yatay seyir', tone: 'neutral', icon: 'remove' },
};

type Phase = 'pick' | 'ready' | 'loading' | 'done' | 'error';

export default function ChartRead() {
  const p = useTheme();
  const params = useLocalSearchParams<{ code?: string }>();
  const pending = useChartRead();
  const [image, setImage] = useState<string | null>(pending.image);
  const [code, setCode] = useState<string | null>(pending.code ?? params.code?.toUpperCase() ?? null);
  const [phase, setPhase] = useState<Phase>(pending.image ? 'ready' : 'pick');
  const [result, setResult] = useState<ChartReading | null>(null);
  const [error, setError] = useState<string | null>(null);
  const autoStarted = useRef(false);

  // Depodaki görüntü bu ekrana alındı; bir dahaki açılışta eskisi görünmesin
  useEffect(() => () => pending.clear(), []); // eslint-disable-line react-hooks/exhaustive-deps

  // Uygulama içi grafikten gelindiyse kullanıcıyı bekletmeden yorumlamaya başla
  useEffect(() => {
    if (pending.source === 'app' && image && !autoStarted.current) {
      autoStarted.current = true;
      run(image);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function run(img = image) {
    if (!img) return;
    setPhase('loading');
    setError(null);
    try {
      const r = await readChart(img, code);
      setResult(r);
      setPhase('done');
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Grafik yorumlanamadı.');
      setPhase('error');
    }
  }

  async function pick(from: 'library' | 'camera') {
    if (from === 'camera') {
      const perm = await ImagePicker.requestCameraPermissionsAsync();
      if (!perm.granted) {
        Alert.alert('Kamera izni gerekli', 'Fotoğraf çekmek için Ayarlar’dan kamera iznini açabilirsiniz.');
        return;
      }
    }
    const opts: ImagePicker.ImagePickerOptions = { mediaTypes: ['images'], quality: 0.7, base64: true };
    const res = from === 'camera' ? await ImagePicker.launchCameraAsync(opts) : await ImagePicker.launchImageLibraryAsync(opts);
    const a = res.canceled ? null : res.assets[0];
    if (!a?.base64) return;
    setImage(`data:${a.mimeType ?? 'image/jpeg'};base64,${a.base64}`);
    setCode(params.code?.toUpperCase() ?? null); // yüklenen görselin hangi varlık olduğunu bilmiyoruz
    setResult(null);
    setPhase('ready');
  }

  function askAssistant() {
    if (!result) return;
    const a = useAssistant.getState();
    a.setLastScreen(image);
    a.setContext(code ? { screen: 'asset_detail', code } : { screen: 'markets' });
    router.replace('/assistant');
  }

  return (
    <ModalShell
      title="Grafik okuma"
      subtitle={code ? `${code} grafiği` : 'Galeriden ya da kameradan bir grafik yükleyin'}
      footer={
        phase === 'ready' ? (
          <Button title="Yorumla" icon="sparkles-outline" onPress={() => run()} />
        ) : phase === 'error' ? (
          <Button title="Tekrar dene" icon="refresh" onPress={() => run()} />
        ) : phase === 'done' ? (
          <View style={styles.footerRow}>
            <Button variant="glass" title="Yeni grafik" icon="images-outline" onPress={() => setPhase('pick')} style={styles.flex} />
            <Button title="Asistana sor" icon="chatbubble-ellipses-outline" onPress={askAssistant} style={styles.flex} />
          </View>
        ) : null
      }
    >
      {/* 1) Görsel seçimi */}
      {phase === 'pick' ? (
        <Animated.View entering={FadeInDown.duration(350)} style={styles.gap12}>
          <PickCard icon="images-outline" title="Galeriden seç" text="Ekran görüntüsü ya da kaydettiğiniz bir grafik" onPress={() => pick('library')} />
          <PickCard icon="camera-outline" title="Fotoğraf çek" text="Bilgisayar ekranındaki ya da basılı bir grafik" onPress={() => pick('camera')} />
          <GlassCard padding={14}>
            <AppText variant="bodyMedium">En iyi sonuç için</AppText>
            {[
              'Grafiğin tamamı ve fiyat ekseni görünsün.',
              'Hisse kodu ve tarih aralığı görselde varsa yorum sayısal veriyle karşılaştırılabilir.',
              'Fotoğraf çekiyorsanız ekrana dik ve yansımasız çekin.',
            ].map((t) => (
              <View key={t} style={styles.tip}>
                <Ionicons name="checkmark-circle-outline" size={16} color={p.accent} />
                <AppText variant="caption" color="textMuted" style={styles.flex}>
                  {t}
                </AppText>
              </View>
            ))}
          </GlassCard>
        </Animated.View>
      ) : null}

      {/* 2) Önizleme */}
      {image && phase !== 'pick' ? (
        <Animated.View entering={FadeIn.duration(300)}>
          <GlassCard padding={8}>
            <Image source={{ uri: image }} style={styles.preview} resizeMode="contain" />
          </GlassCard>
        </Animated.View>
      ) : null}

      {/* 3) Yükleniyor */}
      {phase === 'loading' ? (
        <GlassCard padding={16}>
          <View style={styles.row}>
            <GlassIcon name="sparkles-outline" size={34} />
            <View style={styles.flex}>
              <AppText variant="bodyMedium">Grafik inceleniyor…</AppText>
              <AppText variant="caption" color="textMuted">
                Trend, destek/direnç seviyeleri ve formasyon aranıyor. Bu 5–20 saniye sürebilir.
              </AppText>
            </View>
          </View>
          <View style={styles.skeletons}>
            <Skeleton height={14} width="70%" />
            <Skeleton height={14} />
            <Skeleton height={14} width="85%" />
          </View>
        </GlassCard>
      ) : null}

      {/* 4) Hata */}
      {phase === 'error' && error ? (
        <GlassCard padding={14}>
          <View style={styles.row}>
            <GlassIcon name="alert-circle-outline" size={34} tone="down" />
            <AppText color="down" style={styles.flex}>
              {error}
            </AppText>
          </View>
        </GlassCard>
      ) : null}

      {/* 5) Sonuç */}
      {phase === 'done' && result ? <Result r={result} /> : null}

      {phase === 'done' || phase === 'loading' ? <Disclaimer /> : null}
    </ModalShell>
  );
}

function PickCard({ icon, title, text, onPress }: { icon: IconName; title: string; text: string; onPress: () => void }) {
  const p = useTheme();
  return (
    <Pressable onPress={onPress} accessibilityRole="button" style={({ pressed }) => ({ opacity: pressed ? 0.85 : 1 })}>
      <GlassCard padding={16}>
        <View style={styles.row}>
          <GlassIcon name={icon} size={46} />
          <View style={styles.flex}>
            <AppText variant="heading">{title}</AppText>
            <AppText variant="caption" color="textMuted">
              {text}
            </AppText>
          </View>
          <Ionicons name="chevron-forward" size={18} color={p.textFaint} />
        </View>
      </GlassCard>
    </Pressable>
  );
}

function Result({ r }: { r: ChartReading }) {
  const p = useTheme();
  const t = TREND[r.trend];
  return (
    <Animated.View entering={FadeInDown.duration(400)} style={styles.gap12}>
      <GlassCard padding={16}>
        <View style={styles.row}>
          <GlassIcon name={t.icon} tone={t.tone} size={42} />
          <View style={styles.flex}>
            <AppText variant="caption" color="textMuted">
              TREND
            </AppText>
            <AppText variant="heading">{t.label}</AppText>
          </View>
          {r.pattern ? <Badge label={r.pattern} tone="accent" /> : null}
        </View>
        <AppText color="textMuted" style={styles.mt12}>
          {r.summary}
        </AppText>
      </GlassCard>

      <View style={styles.levels}>
        <Levels title="Destekler" icon="arrow-down-circle-outline" values={r.supports} color={p.up} />
        <Levels title="Dirençler" icon="arrow-up-circle-outline" values={r.resistances} color={p.down} />
      </View>

      {r.indicators_note ? (
        <GlassCard padding={14}>
          <AppText variant="caption" color="textMuted">
            GÖSTERGELER
          </AppText>
          <AppText style={styles.mt4}>{r.indicators_note}</AppText>
        </GlassCard>
      ) : null}

      <View style={[styles.note, { backgroundColor: p.accentSoft }]}>
        <Ionicons name="information-circle-outline" size={16} color={p.accent} />
        <AppText variant="caption" color="textMuted" style={styles.flex}>
          {r.confidence_note}
        </AppText>
      </View>
    </Animated.View>
  );
}

function Levels({ title, icon, values, color }: { title: string; icon: IconName; values: number[]; color: string }) {
  return (
    <GlassCard padding={14} style={styles.flex}>
      <View style={styles.levelHead}>
        <Ionicons name={icon} size={16} color={color} />
        <AppText variant="caption" color="textMuted">
          {title.toUpperCase()}
        </AppText>
      </View>
      {values.length ? (
        values.map((v) => (
          <AppText key={v} variant="number" style={{ color, fontSize: 16, marginTop: 4 }}>
            {formatAxis(v)}
          </AppText>
        ))
      ) : (
        <AppText variant="caption" color="textFaint" style={styles.mt4}>
          Belirgin seviye yok
        </AppText>
      )}
    </GlassCard>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  gap12: { gap: 12 },
  mt4: { marginTop: 4 },
  mt12: { marginTop: 12 },
  tip: { flexDirection: 'row', gap: 8, alignItems: 'flex-start', marginTop: 8 },
  preview: { width: '100%', height: 220, borderRadius: radius.md },
  skeletons: { gap: 8, marginTop: 14 },
  levels: { flexDirection: 'row', gap: 12 },
  levelHead: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  note: { flexDirection: 'row', gap: 8, padding: 12, borderRadius: radius.md, alignItems: 'flex-start' },
  footerRow: { flexDirection: 'row', gap: 10 },
});
