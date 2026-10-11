// Varlık detay: fiyat grafiği + 1/5/20 gün tahmin bandı, model görüşü, uzman yorumu, göstergeler,
// 30/120 gün senaryolar, "İzlemeye al" ve "Aldım".
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { LinearGradient } from 'expo-linear-gradient';
import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useAnalysis, useAsset, useForecast, useHistory } from '@/api/assets';
import type { Analysis, Horizon } from '@/api/types';
import { AnimatedBackground } from '@/components/AnimatedBackground';
import { PriceChart, type ChartMode, type Range } from '@/components/charts/PriceChart';
import { ScenarioChart } from '@/components/charts/ScenarioChart';
import { AppText, Badge, Button, Chips, Disclaimer, GlassCard, GlassIcon, Skeleton, withAlpha, type Tone } from '@/components/ui';
import { formatPct, formatPrice } from '@/lib/format';
import { useWatchlist } from '@/store/watchlist';
import { radius } from '@/theme/colors';
import { useTheme } from '@/theme/ThemeProvider';

const DIRECTION: Record<Analysis['direction'], { label: string; tone: Tone; icon: 'trending-up' | 'trending-down' | 'remove' }> = {
  up: { label: 'Yükseliş yönlü', tone: 'up', icon: 'trending-up' },
  down: { label: 'Düşüş yönlü', tone: 'down', icon: 'trending-down' },
  flat: { label: 'Yatay', tone: 'neutral', icon: 'remove' },
};
const RISK: Record<Analysis['risk'], { label: string; tone: Tone }> = {
  low: { label: 'Düşük risk', tone: 'up' },
  medium: { label: 'Orta risk', tone: 'warn' },
  high: { label: 'Yüksek risk', tone: 'down' },
};
const REGIME: Record<string, string> = { trend: 'Trend', yatay: 'Yatay piyasa', oynak: 'Oynak piyasa' };

export default function AssetDetail() {
  const { code: raw } = useLocalSearchParams<{ code: string }>();
  const code = String(raw ?? '').toUpperCase();
  const p = useTheme();
  const insets = useSafeAreaInsets();

  const [range, setRange] = useState<Range>('3A');
  const [mode, setMode] = useState<ChartMode>('line');
  const [horizon, setHorizon] = useState<Horizon>(5);
  const [scenarioH, setScenarioH] = useState<30 | 120>(30);
  const [w, setW] = useState(0);

  const asset = useAsset(code);
  const history = useHistory(code);
  const forecast = useForecast(code);
  const analysis = useAnalysis(code, horizon);
  const watched = useWatchlist((s) => s.codes.includes(code));
  const toggleWatch = useWatchlist((s) => s.toggle);

  const a = asset.data;
  const type = a?.type ?? 'stock';
  const band = forecast.data?.bands.find((b) => b.model === 'ensemble' && b.horizon === horizon) ?? null;
  const scenario = forecast.data?.scenarios.find((s) => s.horizon === scenarioH);
  const changeTone: Tone = !a ? 'neutral' : a.change_pct > 0 ? 'up' : a.change_pct < 0 ? 'down' : 'neutral';

  function onWatch() {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    toggleWatch(code);
  }

  return (
    <View style={styles.flex}>
      <AnimatedBackground />

      {/* Üst çubuk */}
      <View style={[styles.topBar, { paddingTop: insets.top + 6 }]}>
        <RoundButton icon="chevron-back" label="Geri" onPress={() => router.back()} />
        <View style={styles.titleBox}>
          <AppText variant="heading">{code}</AppText>
          <AppText variant="caption" color="textMuted" numberOfLines={1}>
            {a?.name ?? ' '}
          </AppText>
        </View>
        <RoundButton
          icon={watched ? 'star' : 'star-outline'}
          label={watched ? 'İzlemeden çıkar' : 'İzlemeye al'}
          active={watched}
          onPress={onWatch}
        />
      </View>

      <ScrollView
        style={styles.flex}
        contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 120 }]}
        showsVerticalScrollIndicator={false}
      >
        {/* Fiyat */}
        <Animated.View entering={FadeInDown.duration(350)} style={styles.priceRow}>
          {a ? (
            <>
              <AppText variant="display">{formatPrice(a.last_price, type)} ₺</AppText>
              <View style={styles.priceMeta}>
                <Badge label={formatPct(a.change_pct)} tone={changeTone} />
                <AppText variant="caption" color="textFaint">
                  {type === 'fund' ? 'Fon · günlük fiyat' : 'Hisse · son kapanış'}
                </AppText>
              </View>
            </>
          ) : (
            <>
              <Skeleton width={180} height={34} />
              <Skeleton width={120} height={18} />
            </>
          )}
        </Animated.View>

        {/* Grafik */}
        <Animated.View entering={FadeInDown.delay(60).duration(350)}>
          <GlassCard padding={14}>
            <View style={styles.chartControls}>
              <Chips
                value={range}
                onChange={setRange}
                accessibilityLabel="Zaman aralığı"
                options={(['1A', '3A', '1Y', '5Y'] as Range[]).map((r) => ({ value: r, label: r }))}
              />
              {type === 'stock' ? (
                <Pressable
                  onPress={() => {
                    Haptics.selectionAsync().catch(() => {});
                    setMode((m) => (m === 'line' ? 'candle' : 'line'));
                  }}
                  accessibilityLabel={mode === 'line' ? 'Mum grafiğe geç' : 'Çizgi grafiğe geç'}
                  hitSlop={8}
                  style={[styles.modeBtn, { borderColor: p.glassBorder, backgroundColor: p.inputFill }]}
                >
                  <Ionicons name={mode === 'line' ? 'bar-chart-outline' : 'pulse-outline'} size={16} color={p.textMuted} />
                </Pressable>
              ) : null}
            </View>

            <View onLayout={(e) => setW(e.nativeEvent.layout.width)}>
              {history.data && w > 0 ? (
                <PriceChart history={history.data} range={range} mode={mode} type={type} width={w} band={band} />
              ) : (
                <View style={styles.chartSkeleton}>
                  <Skeleton height={220} radius={12} />
                </View>
              )}
            </View>

            <View style={styles.horizonRow}>
              <AppText variant="caption" color="textMuted">
                Tahmin ufku
              </AppText>
              <Chips
                value={horizon}
                onChange={setHorizon}
                accessibilityLabel="Tahmin ufku"
                options={[
                  { value: 1, label: '1 gün' },
                  { value: 5, label: '5 gün' },
                  { value: 20, label: '20 gün' },
                ]}
              />
            </View>
          </GlassCard>
        </Animated.View>

        {/* Model görüşü */}
        <Animated.View entering={FadeInDown.delay(120).duration(350)}>
          <GlassCard padding={16}>
            {analysis.data ? <AnalysisBlock an={analysis.data} type={type} /> : <AnalysisSkeleton />}
          </GlassCard>
        </Animated.View>

        {/* Uzman yorumu */}
        {analysis.data?.comment ? (
          <Animated.View entering={FadeInDown.delay(160).duration(350)}>
            <GlassCard padding={16}>
              <View style={styles.rowTop}>
                <GlassIcon name="sparkles-outline" size={34} />
                <View style={styles.flex}>
                  <AppText variant="heading">Uzman yorumu</AppText>
                  <AppText color="textMuted" style={styles.mt4}>
                    {analysis.data.comment}
                  </AppText>
                  <AppText variant="caption" color="textFaint" style={styles.mt8}>
                    Yapay zekâ tarafından model çıktılarından üretilmiştir.
                  </AppText>
                </View>
              </View>
            </GlassCard>
          </Animated.View>
        ) : null}

        {/* Göstergeler */}
        {analysis.data ? (
          <Animated.View entering={FadeInDown.delay(200).duration(350)}>
            <AppText variant="heading" style={styles.sectionTitle}>
              Göstergeler
            </AppText>
            <Indicators an={analysis.data} />
          </Animated.View>
        ) : null}

        {/* Senaryolar */}
        <Animated.View entering={FadeInDown.delay(240).duration(350)}>
          <GlassCard padding={14}>
            <View style={styles.rowBetween}>
              <AppText variant="heading">Senaryolar</AppText>
              <Chips
                value={scenarioH}
                onChange={setScenarioH}
                options={[
                  { value: 30, label: '30 gün' },
                  { value: 120, label: '120 gün' },
                ]}
              />
            </View>
            {history.data && scenario && w > 0 ? (
              <View style={styles.mt8}>
                <ScenarioChart closes={history.data.slice(-60).map((x) => x.close)} scenario={scenario} type={type} width={w} />
              </View>
            ) : (
              <View style={styles.mt8}>
                <Skeleton height={200} radius={12} />
              </View>
            )}
            <AppText variant="caption" color="textFaint" style={styles.mt8}>
              Senaryolar olası yolları gösterir; gerçekleşecek fiyatın tahmini değildir.
            </AppText>
          </GlassCard>
        </Animated.View>

        <Disclaimer />
      </ScrollView>

      {/* Alt eylem çubuğu: altta içerik kayarken butonların arkası yumuşakça solar */}
      <View style={[styles.actions, { paddingBottom: Math.max(insets.bottom, 12) }]}>
        <LinearGradient
          colors={[withAlpha(p.bgGradient[p.bgGradient.length - 1], 0), p.bgGradient[p.bgGradient.length - 1]]}
          locations={[0, 0.55]}
          style={StyleSheet.absoluteFill}
          pointerEvents="none"
        />
        <Button
          variant="glass"
          title={watched ? 'İzleniyor' : 'İzlemeye al'}
          icon={watched ? 'star' : 'star-outline'}
          onPress={onWatch}
          style={styles.flex}
        />
        <Button
          title="Aldım"
          icon="add"
          style={styles.flex}
          onPress={() => router.push(`/position/new?code=${code}`)}
        />
      </View>
    </View>
  );
}

// ---- Parçalar -----------------------------------------------------------------------------------

function RoundButton({
  icon,
  label,
  onPress,
  active,
}: {
  icon: 'chevron-back' | 'star' | 'star-outline';
  label: string;
  onPress: () => void;
  active?: boolean;
}) {
  const p = useTheme();
  return (
    <Pressable
      onPress={onPress}
      accessibilityLabel={label}
      hitSlop={8}
      style={[styles.round, { backgroundColor: p.glassFillStrong, borderColor: p.glassBorder }]}
    >
      <Ionicons name={icon} size={20} color={active ? p.warn : p.text} />
    </Pressable>
  );
}

function AnalysisBlock({ an, type }: { an: Analysis; type: 'stock' | 'fund' }) {
  const p = useTheme();
  const d = DIRECTION[an.direction];
  const r = RISK[an.risk];
  const confColor = an.confidence >= 70 ? p.up : an.confidence >= 55 ? p.accent : p.textMuted;

  return (
    <View style={styles.gap12}>
      <View style={styles.rowBetween}>
        <View style={styles.row}>
          <GlassIcon name={d.icon} tone={d.tone} size={38} />
          <View>
            <AppText variant="heading">{d.label} model görüşü</AppText>
            <AppText variant="caption" color="textMuted">
              {an.horizon} günlük ufuk
            </AppText>
          </View>
        </View>
      </View>

      {/* Güven skoru */}
      <View>
        <View style={styles.rowBetween}>
          <AppText variant="caption" color="textMuted">
            Güven skoru
          </AppText>
          <AppText variant="number" style={{ color: confColor, fontSize: 15 }}>
            {an.confidence} / 100
          </AppText>
        </View>
        <View style={[styles.meter, { backgroundColor: p.inputFill }]}>
          <View style={[styles.meterFill, { width: `${an.confidence}%`, backgroundColor: confColor }]} />
        </View>
      </View>

      <View style={styles.badges}>
        <Badge label={r.label} tone={r.tone} />
        <Badge label={REGIME[an.regime] ?? an.regime} />
      </View>

      <AppText color="textMuted">
        Modellere göre {an.horizon} gün sonra fiyatın <AppText style={{ color: p.text }}>%80 olasılıkla</AppText>{' '}
        <AppText variant="number" style={{ color: p.text }}>
          {formatPrice(an.range.low, type)} – {formatPrice(an.range.high, type)}
        </AppText>{' '}
        aralığında olması bekleniyor (orta değer {formatPrice(an.range.mid, type)}).
      </AppText>

      {/* Model ağırlıkları */}
      <View style={styles.gap6}>
        <AppText variant="caption" color="textMuted">
          Model ağırlıkları
        </AppText>
        <View style={[styles.weights, { backgroundColor: p.inputFill }]}>
          {Object.entries(an.weights).map(([k, v], i) => (
            <View
              key={k}
              style={{ flex: v, backgroundColor: i === 0 ? p.accent : p.textFaint, opacity: i === 0 ? 0.85 : 0.6 }}
            />
          ))}
        </View>
        <View style={styles.rowBetween}>
          {Object.entries(an.weights).map(([k, v]) => (
            <AppText key={k} variant="caption" color="textFaint">
              {k === 'timesfm' ? 'TimesFM' : k === 'chronos' ? 'Chronos-2' : k} %{Math.round(v * 100)}
            </AppText>
          ))}
        </View>
      </View>
    </View>
  );
}

function AnalysisSkeleton() {
  return (
    <View style={styles.gap12}>
      <Skeleton width="60%" height={22} />
      <Skeleton height={10} />
      <Skeleton width="40%" height={18} />
      <Skeleton height={40} />
    </View>
  );
}

function Indicators({ an }: { an: Analysis }) {
  const ind = an.indicators;
  const rsi = ind.rsi ?? 0;
  const items: { label: string; value: string; note: string; tone: Tone }[] = [
    {
      label: 'RSI (14)',
      value: rsi.toFixed(1),
      note: rsi > 70 ? 'Aşırı alım bölgesi' : rsi < 30 ? 'Aşırı satım bölgesi' : 'Nötr bölge',
      tone: rsi > 70 ? 'warn' : rsi < 30 ? 'accent' : 'neutral',
    },
    {
      label: 'MACD hist.',
      value: (ind.macd_hist ?? 0).toFixed(2),
      note: (ind.macd_hist ?? 0) >= 0 ? 'Pozitif ivme' : 'Negatif ivme',
      tone: (ind.macd_hist ?? 0) >= 0 ? 'up' : 'down',
    },
    {
      label: 'MA20 / MA50',
      value: ind.ma20_above_ma50 ? 'Üstünde' : 'Altında',
      note: ind.ma20_above_ma50 ? 'Kısa vade ortalaması yukarıda' : 'Kısa vade ortalaması aşağıda',
      tone: ind.ma20_above_ma50 ? 'up' : 'down',
    },
    {
      label: 'ATR %',
      value: `%${(ind.atr_pct ?? 0).toFixed(1)}`,
      note: 'Günlük ortalama oynaklık',
      tone: 'neutral',
    },
  ];
  return (
    <View style={styles.grid}>
      {items.map((it) => (
        <GlassCard key={it.label} padding={12} style={styles.gridItem}>
          <AppText variant="caption" color="textMuted">
            {it.label}
          </AppText>
          <AppText variant="heading" style={styles.mt4}>
            {it.value}
          </AppText>
          <AppText variant="caption" color={it.tone === 'up' ? 'up' : it.tone === 'down' ? 'down' : it.tone === 'warn' ? 'warn' : 'textFaint'}>
            {it.note}
          </AppText>
        </GlassCard>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  rowTop: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  gap6: { gap: 6 },
  gap12: { gap: 12 },
  mt4: { marginTop: 4 },
  mt8: { marginTop: 8 },

  topBar: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingBottom: 8 },
  titleBox: { flex: 1, alignItems: 'center' },
  round: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: StyleSheet.hairlineWidth * 2,
  },

  content: { paddingHorizontal: 18, paddingTop: 8, gap: 14 },
  priceRow: { gap: 6 },
  priceMeta: { flexDirection: 'row', alignItems: 'center', gap: 8 },

  chartControls: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 },
  modeBtn: {
    width: 34,
    height: 30,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: StyleSheet.hairlineWidth * 2,
  },
  chartSkeleton: { paddingTop: 38 },
  horizonRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 10, gap: 8 },

  meter: { height: 8, borderRadius: 4, overflow: 'hidden', marginTop: 6 },
  meterFill: { height: '100%', borderRadius: 4 },
  badges: { flexDirection: 'row', gap: 6 },
  weights: { flexDirection: 'row', height: 8, borderRadius: 4, overflow: 'hidden', gap: 2 },

  sectionTitle: { marginBottom: 8, marginLeft: 2 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  gridItem: { width: '47%', flexGrow: 1 },

  actions: { position: 'absolute', left: 0, right: 0, bottom: 0, flexDirection: 'row', gap: 10, paddingHorizontal: 16, paddingTop: 10 },
});
