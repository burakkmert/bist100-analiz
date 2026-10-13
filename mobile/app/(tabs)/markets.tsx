// Piyasalar: Hisse / Fon, arama ve tarayıcı filtreleri (yön, en az güven).
import { useEffect, useState } from 'react';
import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';

import { useAssets, useScreener } from '@/api/assets';
import type { Direction } from '@/api/types';
import { AssetRow } from '@/components/AssetRow';
import { Segmented } from '@/components/Segmented';
import { AppText, Chips, GlassCard, Screen, Skeleton, TextField } from '@/components/ui';
import { useTheme } from '@/theme/ThemeProvider';

type DirFilter = 'all' | Direction;
type ConfFilter = 0 | 60 | 70;

export default function Markets() {
  const p = useTheme();
  const [tab, setTab] = useState<'stock' | 'fund'>('stock');
  const [q, setQ] = useState('');
  const [debounced, setDebounced] = useState('');
  const [dir, setDir] = useState<DirFilter>('all');
  const [conf, setConf] = useState<ConfFilter>(0);

  // Her tuşta istek atmamak için kısa bekleme
  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 250);
    return () => clearTimeout(t);
  }, [q]);

  const filtered = dir !== 'all' || conf > 0;
  const list = useAssets(tab, debounced);
  const screener = useScreener({ type: tab, direction: dir === 'all' ? undefined : dir, min_conf: conf || undefined });

  const source = filtered ? screener : list;
  const norm = (s: string) => s.toLocaleLowerCase('tr-TR');
  const items = (source.data ?? []).filter(
    (a) => !filtered || !debounced || norm(a.code).includes(norm(debounced)) || norm(a.name).includes(norm(debounced)),
  );

  return (
    <Screen tabBarSpace>
      <View style={styles.titleRow}>
        <AppText variant="title">Piyasalar</AppText>
        <Pressable
          onPress={() => router.push('/chart-read')}
          accessibilityLabel="Grafik yükleyip yorumlat"
          hitSlop={8}
          style={[styles.chartBtn, { backgroundColor: p.accentSoft, borderColor: p.accent }]}
        >
          <Ionicons name="scan-outline" size={16} color={p.accent} />
          <AppText variant="caption" color="accent">
            Grafik oku
          </AppText>
        </Pressable>
      </View>
      <Segmented
        value={tab}
        onChange={setTab}
        options={[
          { value: 'stock', label: 'Hisseler' },
          { value: 'fund', label: 'Fonlar' },
        ]}
      />
      <TextField icon="search-outline" placeholder="Kod veya ad ara" value={q} onChangeText={setQ} autoCorrect={false} />

      {/* Tarayıcı */}
      <View style={styles.filters}>
        <View style={styles.filterRow}>
          <AppText variant="caption" color="textMuted" style={styles.filterLabel}>
            Model yönü
          </AppText>
          <Chips
            value={dir}
            onChange={setDir}
            options={[
              { value: 'all', label: 'Tümü' },
              { value: 'up', label: 'Yükseliş' },
              { value: 'down', label: 'Düşüş' },
              { value: 'flat', label: 'Yatay' },
            ]}
          />
        </View>
        <View style={styles.filterRow}>
          <AppText variant="caption" color="textMuted" style={styles.filterLabel}>
            En az güven
          </AppText>
          <Chips
            value={conf}
            onChange={setConf}
            options={[
              { value: 0, label: 'Tümü' },
              { value: 60, label: '60+' },
              { value: 70, label: '70+' },
            ]}
          />
        </View>
      </View>

      <GlassCard padding={0}>
        {source.isLoading ? (
          <View style={styles.loading}>
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} height={38} />
            ))}
          </View>
        ) : source.isError ? (
          <AppText color="down" style={styles.empty}>
            Veriler alınamadı. Bağlantınızı kontrol edin.
          </AppText>
        ) : items.length === 0 ? (
          <AppText color="textMuted" style={styles.empty}>
            {filtered ? 'Bu filtrelere uyan varlık yok.' : 'Sonuç bulunamadı.'}
          </AppText>
        ) : (
          items.map((a, i) => <AssetRow key={a.code} a={a} first={i === 0} />)
        )}
      </GlassCard>
      {filtered ? (
        <AppText variant="caption" color="textFaint">
          Filtreler 5 günlük model görüşüne göre uygulanır.
        </AppText>
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  titleRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  chartBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: 999,
    borderWidth: StyleSheet.hairlineWidth * 2,
  },
  filters: { gap: 10 },
  filterRow: { gap: 6 },
  filterLabel: { marginLeft: 4 },
  loading: { padding: 16, gap: 12 },
  empty: { padding: 20, textAlign: 'center' },
});
