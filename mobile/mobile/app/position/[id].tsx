// Pozisyon detayı: kâr/zarar özeti, "Sattım" akışı (açıksa), kaydı silme.
import * as Haptics from 'expo-haptics';
import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Alert, StyleSheet, View } from 'react-native';

import { ModalShell } from '@/components/ModalShell';
import { AppText, Badge, Button, Chips, GlassCard, TextField } from '@/components/ui';
import { formatDate, formatPct, formatPrice, formatTRY } from '@/lib/format';
import { isoToTr, parseNumber, todayISO, trToIso, usePortfolioView } from '@/lib/portfolio';
import { usePortfolio } from '@/store/portfolio';
import { useTheme } from '@/theme/ThemeProvider';

export default function PositionDetail() {
  const p = useTheme();
  const { id } = useLocalSearchParams<{ id: string }>();
  const view = usePortfolioView();
  const sell = usePortfolio((s) => s.sell);
  const remove = usePortfolio((s) => s.remove);
  const pos = [...view.open, ...view.closed].find((x) => x.id === id);

  const type = pos?.asset?.type ?? 'stock';
  const [selling, setSelling] = useState(false);
  const [price, setPrice] = useState(pos ? formatPrice(pos.price, type) : '');
  const [dateMode, setDateMode] = useState<'today' | 'other'>('today');
  const [dateText, setDateText] = useState(isoToTr(todayISO()));
  const [errors, setErrors] = useState<Record<string, string>>({});

  if (!pos) {
    return (
      <ModalShell title="Pozisyon">
        <AppText color="textMuted">Bu kayıt bulunamadı.</AppText>
      </ModalShell>
    );
  }

  const pnlTone = pos.pnl > 0 ? 'up' : pos.pnl < 0 ? 'down' : 'neutral';
  const priceN = parseNumber(price);
  const previewPnl = priceN ? (priceN - pos.buy_price) * pos.qty : null;

  function confirmSell() {
    const e: Record<string, string> = {};
    if (!priceN || priceN <= 0) e.price = 'Geçerli bir fiyat girin.';
    const iso = dateMode === 'today' ? todayISO() : trToIso(dateText);
    if (!iso) e.date = 'Tarihi GG.AA.YYYY biçiminde girin (gelecek tarih olamaz).';
    else if (pos && iso < pos.buy_date) e.date = 'Satış tarihi alış tarihinden önce olamaz.';
    setErrors(e);
    if (Object.keys(e).length || !priceN || !iso || !pos) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning).catch(() => {});
      return;
    }
    sell(pos.id, priceN, iso);
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    router.back();
  }

  function confirmDelete() {
    Alert.alert('Kaydı sil', 'Bu kayıt portföy defterinizden kalıcı olarak silinecek.', [
      { text: 'Vazgeç', style: 'cancel' },
      {
        text: 'Sil',
        style: 'destructive',
        onPress: () => {
          remove(pos!.id);
          router.back();
        },
      },
    ]);
  }

  return (
    <ModalShell
      title={pos.code}
      subtitle={pos.asset?.name}
      footer={
        pos.open ? (
          selling ? (
            <>
              <Button title="Satışı kaydet" icon="checkmark" onPress={confirmSell} />
              <Button variant="ghost" title="Vazgeç" onPress={() => setSelling(false)} />
            </>
          ) : (
            <>
              <Button title="Sattım" icon="arrow-up-circle-outline" onPress={() => setSelling(true)} />
              <Button variant="ghost" title="Kaydı sil" onPress={confirmDelete} />
            </>
          )
        ) : (
          <Button variant="ghost" title="Kaydı sil" onPress={confirmDelete} />
        )
      }
    >
      {/* Özet */}
      <GlassCard padding={18}>
        <View style={styles.rowBetween}>
          <AppText variant="caption" color="textMuted">
            {pos.open ? 'GÜNCEL DEĞER' : 'SATIŞ TUTARI'}
          </AppText>
          <Badge label={pos.open ? 'Açık' : 'Kapandı'} tone={pos.open ? 'accent' : 'neutral'} />
        </View>
        <AppText variant="display" style={styles.mv4}>
          {formatTRY(pos.value)}
        </AppText>
        <AppText variant="bodyMedium" color={pnlTone === 'up' ? 'up' : pnlTone === 'down' ? 'down' : 'textMuted'}>
          {pos.pnl >= 0 ? '+' : '−'}
          {formatTRY(Math.abs(pos.pnl))} ({formatPct(pos.pnlPct)}) {pos.open ? 'kâr/zarar' : 'gerçekleşen'}
        </AppText>
      </GlassCard>

      <GlassCard padding={4}>
        <Row label="Adet" value={String(pos.qty).replace('.', ',')} />
        <Row label="Alış fiyatı" value={formatPrice(pos.buy_price, type)} />
        <Row label="Alış tarihi" value={formatDate(pos.buy_date)} />
        <Row label="Maliyet" value={formatTRY(pos.cost)} />
        {pos.open ? (
          <Row label="Güncel fiyat" value={formatPrice(pos.price, type)} />
        ) : (
          <>
            <Row label="Satış fiyatı" value={formatPrice(pos.sell_price ?? 0, type)} />
            <Row label="Satış tarihi" value={pos.sell_date ? formatDate(pos.sell_date) : '—'} last />
          </>
        )}
        {pos.open ? <Row label="Bugünkü değişim" value={`${pos.dayPnl >= 0 ? '+' : '−'}${formatTRY(Math.abs(pos.dayPnl))}`} last /> : null}
      </GlassCard>

      {/* Satış formu */}
      {selling ? (
        <View style={styles.gap12}>
          <AppText variant="heading">Satış bilgileri</AppText>
          <TextField
            label="Satış fiyatı (₺)"
            keyboardType="decimal-pad"
            value={price}
            onChangeText={setPrice}
            error={errors.price}
            autoFocus
          />
          <View style={styles.gap8}>
            <AppText variant="caption" color="textMuted" style={styles.label}>
              Satış tarihi
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
              <TextField
                placeholder="GG.AA.YYYY"
                keyboardType="numbers-and-punctuation"
                value={dateText}
                onChangeText={setDateText}
                error={errors.date}
                icon="calendar-outline"
              />
            ) : null}
          </View>
          {previewPnl !== null ? (
            <View style={[styles.preview, { backgroundColor: previewPnl >= 0 ? `${p.up}22` : `${p.down}22` }]}>
              <AppText color="textMuted">Gerçekleşecek kâr/zarar</AppText>
              <AppText variant="number" style={{ color: previewPnl >= 0 ? p.up : p.down, fontSize: 17 }}>
                {previewPnl >= 0 ? '+' : '−'}
                {formatTRY(Math.abs(previewPnl))}
              </AppText>
            </View>
          ) : null}
        </View>
      ) : null}

      <AppText variant="caption" color="textFaint">
        Kâr/zarar komisyon ve vergileri içermez.
      </AppText>
    </ModalShell>
  );
}

function Row({ label, value, last }: { label: string; value: string; last?: boolean }) {
  const p = useTheme();
  return (
    <View style={[styles.row, !last && { borderBottomWidth: StyleSheet.hairlineWidth * 2, borderBottomColor: p.separator }]}>
      <AppText color="textMuted">{label}</AppText>
      <AppText variant="number" style={{ color: p.text, fontSize: 15 }}>
        {value}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  mv4: { marginVertical: 4 },
  gap8: { gap: 8 },
  gap12: { gap: 12 },
  label: { marginLeft: 4 },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 14, paddingVertical: 12 },
  preview: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 14, borderRadius: 16 },
});
