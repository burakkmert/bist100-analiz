// "Aldım" formu: varlık, adet, fiyat, tarih. Detaydan ya da sinyalden gelindiyse önceden dolu.
import * as Haptics from 'expo-haptics';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useMemo, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { useAssets } from '@/api/assets';
import { DateField } from '@/components/DateField';
import { ModalShell } from '@/components/ModalShell';
import { AppText, Button, Chips, GlassCard, TextField } from '@/components/ui';
import { formatPrice, formatTRY } from '@/lib/format';
import { isoToTr, parseNumber, todayISO, trToIso } from '@/lib/portfolio';
import { usePortfolio } from '@/store/portfolio';
import { radius } from '@/theme/colors';
import { useTheme } from '@/theme/ThemeProvider';

export default function NewPosition() {
  const p = useTheme();
  const params = useLocalSearchParams<{ code?: string; signal?: string }>();
  const add = usePortfolio((s) => s.add);
  const assets = useAssets();

  const [code, setCode] = useState((params.code ?? '').toUpperCase());
  const [query, setQuery] = useState('');
  const [qty, setQty] = useState('');
  const [price, setPrice] = useState('');
  const [dateMode, setDateMode] = useState<'today' | 'other'>('today');
  const [dateText, setDateText] = useState(isoToTr(todayISO()));
  const [errors, setErrors] = useState<Record<string, string>>({});

  const asset = assets.data?.find((a) => a.code === code);

  // Varlık seçilince fiyatı son fiyatla doldur (kullanıcı değiştirebilir)
  useEffect(() => {
    if (asset && !price) setPrice(formatPrice(asset.last_price, asset.type));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [asset?.code]);

  const suggestions = useMemo(() => {
    if (!query.trim()) return [];
    const n = (s: string) => s.toLocaleLowerCase('tr-TR');
    return (assets.data ?? [])
      .filter((a) => n(a.code).includes(n(query)) || n(a.name).includes(n(query)))
      .slice(0, 5);
  }, [assets.data, query]);

  const qtyN = parseNumber(qty);
  const priceN = parseNumber(price);
  const total = qtyN && priceN ? qtyN * priceN : null;

  function save() {
    const e: Record<string, string> = {};
    if (!asset) e.code = 'Bir varlık seçin.';
    if (!qtyN || qtyN <= 0) e.qty = 'Geçerli bir adet girin.';
    if (!priceN || priceN <= 0) e.price = 'Geçerli bir fiyat girin.';
    const iso = dateMode === 'today' ? todayISO() : trToIso(dateText);
    if (!iso) e.date = 'Tarihi GG.AA.YYYY biçiminde girin (gelecek tarih olamaz).';
    setErrors(e);
    if (Object.keys(e).length || !asset || !qtyN || !priceN || !iso) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning).catch(() => {});
      return;
    }
    add({ code: asset.code, qty: qtyN, buy_price: priceN, buy_date: iso, signal_id: params.signal ? Number(params.signal) : null });
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    router.back();
  }

  return (
    <ModalShell
      title="Aldım"
      subtitle="Aracı kurumunuzda yaptığınız alımı kaydedin"
      footer={
        <>
          <Button title="Kaydet" icon="checkmark" onPress={save} />
          <AppText variant="caption" color="textFaint" style={styles.center}>
            Uygulama işlem yapmaz; bu kayıt yalnızca kendi takibiniz içindir.
          </AppText>
        </>
      }
    >
      {/* Varlık */}
      {asset ? (
        <GlassCard padding={14}>
          <View style={styles.rowBetween}>
            <View style={styles.flex}>
              <AppText variant="heading">{asset.code}</AppText>
              <AppText variant="caption" color="textMuted" numberOfLines={1}>
                {asset.name} · son fiyat {formatPrice(asset.last_price, asset.type)}
              </AppText>
            </View>
            {!params.code ? (
              <Pressable onPress={() => setCode('')} hitSlop={8}>
                <AppText variant="caption" color="accent">
                  Değiştir
                </AppText>
              </Pressable>
            ) : null}
          </View>
        </GlassCard>
      ) : (
        <View style={styles.gap8}>
          <TextField
            label="Varlık"
            icon="search-outline"
            placeholder="Kod veya ad yazın (ör. THYAO)"
            value={query}
            onChangeText={setQuery}
            autoCapitalize="characters"
            autoCorrect={false}
            error={errors.code}
          />
          {suggestions.length ? (
            <GlassCard padding={0}>
              {suggestions.map((a, i) => (
                <Pressable
                  key={a.code}
                  onPress={() => {
                    Haptics.selectionAsync().catch(() => {});
                    setCode(a.code);
                    setQuery('');
                    setPrice('');
                  }}
                  style={({ pressed }) => [
                    styles.suggestion,
                    i > 0 && { borderTopWidth: StyleSheet.hairlineWidth * 2, borderTopColor: p.separator },
                    pressed && { backgroundColor: p.glassFill },
                  ]}
                >
                  <AppText variant="bodyMedium">{a.code}</AppText>
                  <AppText variant="caption" color="textMuted" numberOfLines={1} style={styles.flex}>
                    {a.name}
                  </AppText>
                </Pressable>
              ))}
            </GlassCard>
          ) : null}
        </View>
      )}

      <View style={styles.row2}>
        <View style={styles.flex}>
          <TextField
            label="Adet"
            placeholder="0"
            keyboardType="decimal-pad"
            value={qty}
            onChangeText={setQty}
            error={errors.qty}
          />
        </View>
        <View style={styles.flex}>
          <TextField
            label="Alış fiyatı (₺)"
            placeholder="0,00"
            keyboardType="decimal-pad"
            value={price}
            onChangeText={setPrice}
            error={errors.price}
          />
        </View>
      </View>

      <View style={styles.gap8}>
        <AppText variant="caption" color="textMuted" style={styles.label}>
          Alış tarihi
        </AppText>
        <Chips
          value={dateMode}
          onChange={setDateMode}
          options={[
            { value: 'today', label: 'Bugün' },
            { value: 'other', label: 'Başka bir gün' },
          ]}
        />
        {dateMode === 'other' ? (
          <DateField
            value={dateText}
            onChange={setDateText}
            error={errors.date}
            accessibilityLabel="Alış tarihi"
          />
        ) : null}
      </View>

      {total ? (
        <View style={[styles.total, { backgroundColor: p.accentSoft }]}>
          <AppText color="textMuted">Toplam tutar</AppText>
          <AppText variant="number" style={{ color: p.text, fontSize: 17 }}>
            {formatTRY(total)}
          </AppText>
        </View>
      ) : null}
    </ModalShell>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  center: { textAlign: 'center' },
  gap8: { gap: 8 },
  label: { marginLeft: 4 },
  row2: { flexDirection: 'row', gap: 12 },
  rowBetween: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  suggestion: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 16, paddingVertical: 12 },
  total: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 14,
    borderRadius: radius.md,
  },
});
