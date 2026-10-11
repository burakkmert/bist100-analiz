// Portföy defteri: özet, açık / kapanmış pozisyonlar, izleme listesi.
import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';

import { useAssets } from '@/api/assets';
import { AssetRow } from '@/components/AssetRow';
import { Segmented } from '@/components/Segmented';
import { AppText, Button, GlassCard, GlassIcon, Screen, Skeleton } from '@/components/ui';
import { formatDate, formatPct, formatPrice, formatTRY } from '@/lib/format';
import { usePortfolioView, type PositionView } from '@/lib/portfolio';
import { useWatchlist } from '@/store/watchlist';
import { useTheme } from '@/theme/ThemeProvider';

export default function Portfolio() {
  const p = useTheme();
  const view = usePortfolioView();
  const [tab, setTab] = useState<'open' | 'closed'>('open');
  const s = view.summary;
  const hasAny = view.open.length + view.closed.length > 0;
  const list = tab === 'open' ? view.open : view.closed;

  return (
    <Screen tabBarSpace>
      <View style={styles.titleRow}>
        <AppText variant="title">Portföy</AppText>
        {hasAny ? (
          <Pressable
            onPress={() => router.push('/position/new')}
            accessibilityLabel="Aldım kaydı ekle"
            hitSlop={8}
            style={[styles.addBtn, { backgroundColor: p.accentSoft, borderColor: p.accent }]}
          >
            <Ionicons name="add" size={18} color={p.accent} />
            <AppText variant="caption" color="accent">
              Aldım
            </AppText>
          </Pressable>
        ) : null}
      </View>

      {!hasAny ? (
        <GlassCard padding={24}>
          <View style={styles.empty}>
            <GlassIcon name="briefcase-outline" size={60} />
            <AppText variant="heading">Portföy defteriniz boş</AppText>
            <AppText color="textMuted" style={styles.center}>
              Uygulama aracı kurumunuza bağlanmaz. İşlemi kendi kurumunuzda yaptıktan sonra burada "Aldım" diye
              kaydederek kâr/zararınızı takip edebilirsiniz.
            </AppText>
            <Button title="Aldım kaydı ekle" icon="add" onPress={() => router.push('/position/new')} style={styles.button} />
          </View>
        </GlassCard>
      ) : (
        <>
          {/* Özet */}
          <Animated.View entering={FadeInDown.duration(350)}>
            <GlassCard padding={18}>
              <AppText variant="caption" color="textMuted">
                PORTFÖY DEĞERİ
              </AppText>
              {view.loading ? (
                <Skeleton width={180} height={34} />
              ) : (
                <AppText variant="display" style={styles.mv4}>
                  {formatTRY(s.value)}
                </AppText>
              )}
              <View style={styles.stats}>
                <Stat label="Bugün" value={s.dayPnl} pct={s.dayPct} />
                <Stat label="Toplam (açık)" value={s.unrealized} pct={s.unrealizedPct} />
                <Stat label="Gerçekleşen" value={s.realized} />
              </View>
            </GlassCard>
          </Animated.View>

          <Segmented
            value={tab}
            onChange={setTab}
            options={[
              { value: 'open', label: `Açık (${view.open.length})` },
              { value: 'closed', label: `Kapanmış (${view.closed.length})` },
            ]}
          />

          <GlassCard padding={0}>
            {list.length === 0 ? (
              <AppText color="textMuted" style={styles.emptyList}>
                {tab === 'open' ? 'Açık pozisyonunuz yok.' : 'Henüz kapanmış pozisyon yok.'}
              </AppText>
            ) : (
              list.map((pos, i) => <PositionRow key={pos.id} pos={pos} first={i === 0} />)
            )}
          </GlassCard>
          <AppText variant="caption" color="textFaint">
            Kâr/zarar komisyon ve vergileri içermez.
          </AppText>
        </>
      )}

      <WatchlistCard />
    </Screen>
  );
}

function Stat({ label, value, pct }: { label: string; value: number; pct?: number }) {
  const p = useTheme();
  const color = value > 0 ? p.up : value < 0 ? p.down : p.textMuted;
  return (
    <View style={styles.stat}>
      <AppText variant="caption" color="textFaint">
        {label}
      </AppText>
      <AppText variant="number" style={{ color, fontSize: 14 }}>
        {value >= 0 ? '+' : '−'}
        {formatTRY(Math.abs(value))}
      </AppText>
      {pct !== undefined ? (
        <AppText variant="caption" style={{ color }}>
          {formatPct(pct)}
        </AppText>
      ) : null}
    </View>
  );
}

function PositionRow({ pos, first }: { pos: PositionView; first?: boolean }) {
  const p = useTheme();
  const color = pos.pnl > 0 ? p.up : pos.pnl < 0 ? p.down : p.textMuted;
  const type = pos.asset?.type ?? 'stock';
  return (
    <Pressable
      onPress={() => router.push(`/position/${pos.id}`)}
      accessibilityRole="button"
      style={({ pressed }) => [
        styles.posRow,
        !first && { borderTopWidth: StyleSheet.hairlineWidth * 2, borderTopColor: p.separator },
        pressed && { backgroundColor: p.glassFill },
      ]}
    >
      <View style={styles.flex}>
        <AppText variant="heading">{pos.code}</AppText>
        <AppText variant="caption" color="textMuted" numberOfLines={1}>
          {String(pos.qty).replace('.', ',')} adet · {formatPrice(pos.buy_price, type)} ·{' '}
          {formatDate(pos.open ? pos.buy_date : (pos.sell_date ?? pos.buy_date))}
        </AppText>
      </View>
      <View style={styles.right}>
        <AppText variant="number" style={{ color: p.text, fontSize: 15 }}>
          {formatTRY(pos.value)}
        </AppText>
        <AppText variant="caption" style={{ color }}>
          {pos.pnl >= 0 ? '+' : '−'}
          {formatTRY(Math.abs(pos.pnl))} · {formatPct(pos.pnlPct)}
        </AppText>
      </View>
      <Ionicons name="chevron-forward" size={16} color={p.textFaint} />
    </Pressable>
  );
}

function WatchlistCard() {
  const codes = useWatchlist((s) => s.codes);
  const all = useAssets();
  const items = (all.data ?? []).filter((a) => codes.includes(a.code));

  return (
    <View style={styles.section}>
      <AppText variant="heading">İzleme listesi</AppText>
      <GlassCard padding={codes.length ? 0 : 16}>
        {codes.length === 0 ? (
          <View style={styles.row}>
            <GlassIcon name="star-outline" size={40} tone="neutral" />
            <AppText variant="caption" color="textMuted" style={styles.flex}>
              Bir varlığın detayında yıldıza dokunarak izleme listenize ekleyebilirsiniz.
            </AppText>
          </View>
        ) : all.isLoading ? (
          <View style={styles.loading}>
            {codes.map((c) => (
              <Skeleton key={c} height={38} />
            ))}
          </View>
        ) : (
          items.map((a, i) => <AssetRow key={a.code} a={a} first={i === 0} />)
        )}
      </GlassCard>
    </View>
  );
}

const styles = StyleSheet.create({
  titleRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  addBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: 999,
    borderWidth: StyleSheet.hairlineWidth * 2,
  },
  mv4: { marginVertical: 4 },
  stats: { flexDirection: 'row', marginTop: 10, gap: 8 },
  stat: { flex: 1, gap: 2 },
  emptyList: { padding: 20, textAlign: 'center' },
  posRow: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 13, gap: 12 },
  right: { alignItems: 'flex-end', gap: 2 },
  section: { gap: 8 },
  loading: { padding: 16, gap: 12 },
  empty: { alignItems: 'center', gap: 10 },
  center: { textAlign: 'center' },
  button: { alignSelf: 'stretch', marginTop: 6 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  flex: { flex: 1, gap: 2 },
});
