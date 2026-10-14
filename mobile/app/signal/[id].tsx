// Sinyal detayı: bildirime ya da ana sayfadaki sinyal kartına dokununca açılır.
// Sinyalin kendisi (yön, ufuk, güven, stop seviyesi, sonuç) + "Neden bu sinyal?" (modelin analizi).
// Dil kuralı: emir kipi yok; "alım yönlü model sinyali" denir, "al" denmez.
import { router, useLocalSearchParams } from 'expo-router';
import { StyleSheet, View } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';

import { useAnalysis, useAsset, useSignals } from '@/api/assets';
import type { Horizon, Indicators } from '@/api/types';
import { ModalShell } from '@/components/ModalShell';
import { AppText, Badge, Button, Disclaimer, GlassCard, GlassIcon, Skeleton } from '@/components/ui';
import { formatDate, formatPct, formatPrice } from '@/lib/format';

const REGIME = { trend: 'Trend', range: 'Yatay piyasa', high_vol: 'Oynak piyasa' } as const;
const RISK = { low: 'Düşük', medium: 'Orta', high: 'Yüksek' } as const;

/** Sinyal ufku 30 olabilir; analiz yalnızca 1/5/20 günde var → en yakın kısa ufuk */
const toAnalysisHorizon = (h: number): Horizon => (h <= 1 ? 1 : h <= 5 ? 5 : 20);

export default function SignalDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const signals = useSignals();
  const signal = signals.data?.find((s) => String(s.id) === String(id));
  const code = signal?.code ?? '';
  const asset = useAsset(code);
  const analysis = useAnalysis(code, toAnalysisHorizon(signal?.horizon ?? 5));

  if (signals.isLoading) {
    return (
      <ModalShell title="Model sinyali">
        <GlassCard padding={16}>
          <Skeleton height={20} width="50%" />
          <View style={styles.mt12}>
            <Skeleton height={14} />
          </View>
        </GlassCard>
      </ModalShell>
    );
  }

  if (!signal) {
    return (
      <ModalShell title="Model sinyali" footer={<Button variant="glass" title="Kapat" onPress={() => router.back()} />}>
        <GlassCard padding={16}>
          <View style={styles.row}>
            <GlassIcon name="time-outline" size={40} tone="neutral" />
            <AppText color="textMuted" style={styles.flex}>
              Bu sinyal artık açık değil ya da bulunamadı. Sinyaller ufukları dolunca kapanır.
            </AppText>
          </View>
        </GlassCard>
      </ModalShell>
    );
  }

  const up = signal.side === 'buy';
  const type = asset.data?.type ?? 'stock';
  const an = analysis.data;
  const ind: Indicators = an?.indicators ?? {};

  return (
    <ModalShell
      title={signal.code}
      subtitle={asset.data?.name ?? 'Model sinyali'}
      footer={
        <View style={styles.footer}>
          <Button variant="glass" title="Varlığa git" icon="stats-chart-outline" style={styles.flex} onPress={() => router.push(`/asset/${signal.code}`)} />
          <Button
            title="Aldım"
            icon="add-circle-outline"
            style={styles.flex}
            onPress={() => router.push(`/position/new?code=${signal.code}&signal=${signal.id}`)}
          />
        </View>
      }
    >
      <Animated.View entering={FadeInDown.duration(350)} style={styles.gap}>
        <GlassCard padding={16}>
          <View style={styles.row}>
            <GlassIcon name={up ? 'trending-up' : 'trending-down'} tone={up ? 'up' : 'down'} size={46} />
            <View style={styles.flex}>
              <AppText variant="heading">
                {signal.horizon} günlük ufukta {up ? 'yükseliş' : 'düşüş'} yönlü model sinyali
              </AppText>
              <AppText variant="caption" color="textMuted">
                {formatDate(signal.created_at.slice(0, 10))} tarihinde oluştu
              </AppText>
            </View>
          </View>
          <View style={styles.badges}>
            <Badge label={up ? 'Alım yönlü' : 'Satış yönlü'} tone={up ? 'up' : 'down'} />
            <Badge label={`Güven ${signal.confidence}/100`} tone="accent" />
          </View>
          <View style={styles.stats}>
            <Stat label="Stop seviyesi" value={signal.stop_level != null ? `${formatPrice(signal.stop_level, type)} ₺` : '—'} />
            <Stat label="Önerilen adet" value={signal.suggested_qty != null ? String(signal.suggested_qty) : '—'} />
            <Stat label="Ufuk" value={`${signal.horizon} gün`} />
          </View>
          {signal.outcome ? (
            <AppText variant="caption" color={signal.outcome.hit ? 'up' : 'down'} style={styles.mt12}>
              Sonuç: gerçekleşen {formatPct(signal.outcome.realized)} · {signal.outcome.hit ? 'model yönü doğru çıktı' : 'model yönü tutmadı'}
            </AppText>
          ) : null}
        </GlassCard>

        <AppText variant="caption" color="textMuted" style={styles.section}>
          NEDEN BU SİNYAL?
        </AppText>
        <GlassCard padding={16}>
          {!an ? (
            <Skeleton height={60} />
          ) : (
            <>
              <AppText>
                Modeller {an.horizon} günlük ufukta{' '}
                {an.direction === 'up' ? 'yükseliş' : an.direction === 'down' ? 'düşüş' : 'yatay seyir'} yönünde uzlaşıyor (güven{' '}
                {an.confidence}/100). %80 olasılık aralığı {formatPrice(an.range.low, type)} – {formatPrice(an.range.high, type)} ₺.
              </AppText>
              <View style={styles.badges}>
                <Badge label={`Risk: ${RISK[an.risk]}`} />
                {an.regime ? <Badge label={REGIME[an.regime]} /> : null}
              </View>
              <View style={styles.stats}>
                <Stat label="RSI (14)" value={ind.rsi != null ? ind.rsi.toFixed(1) : '—'} />
                <Stat label="MACD hist." value={ind.macd_hist != null ? ind.macd_hist.toFixed(2) : '—'} />
                <Stat label="MA20 > MA50" value={ind.ma20_above_ma50 == null ? '—' : ind.ma20_above_ma50 ? 'Evet' : 'Hayır'} />
              </View>
              {an.weights ? (
                <AppText variant="caption" color="textMuted" style={styles.mt12}>
                  Model ağırlıkları:{' '}
                  {Object.entries(an.weights)
                    .map(([k, v]) => `${k} %${Math.round(v * 100)}`)
                    .join(' · ')}
                </AppText>
              ) : null}
              {an.comment ? (
                <AppText color="textMuted" style={styles.mt12}>
                  {an.comment}
                </AppText>
              ) : null}
            </>
          )}
        </GlassCard>
        <Disclaimer />
      </Animated.View>
    </ModalShell>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.stat}>
      <AppText variant="caption" color="textFaint">
        {label}
      </AppText>
      <AppText variant="bodyMedium">{value}</AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  gap: { gap: 12 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  badges: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 12 },
  stats: { flexDirection: 'row', gap: 10, marginTop: 14 },
  stat: { flex: 1, gap: 2 },
  section: { marginTop: 6, marginBottom: -4, marginLeft: 4 },
  footer: { flexDirection: 'row', gap: 10 },
  mt12: { marginTop: 12 },
});
