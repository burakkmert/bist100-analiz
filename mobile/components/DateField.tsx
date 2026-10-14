// Tarih seçici alanı: dokununca takvim açılır.
// • iOS: alttan açılan panelde takvim (inline) + "Tamam"
// • Android: sistemin tarih penceresi
// Değer "GG.AA.YYYY" metni olarak tutulur (formlardaki trToIso ile uyumlu); gelecekteki tarih seçilemez.
import { Ionicons } from '@expo/vector-icons';
import DateTimePicker, { DateTimePickerAndroid, type DateTimePickerEvent } from '@react-native-community/datetimepicker';
import * as Haptics from 'expo-haptics';
import { useState } from 'react';
import { Modal, Platform, Pressable, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppText, Button, GlassCard } from '@/components/ui';
import { isoToTr, trToIso } from '@/lib/portfolio';
import { radius } from '@/theme/colors';
import { useTheme } from '@/theme/ThemeProvider';

interface Props {
  /** "13.10.2026" */
  value: string;
  onChange: (tr: string) => void;
  error?: string;
  /** "2026-10-01" — bundan önceki günler seçilemez (ör. satış tarihi alıştan önce olamaz) */
  minimumISO?: string;
  accessibilityLabel?: string;
}

const toDate = (iso: string) => {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d);
};
const toISO = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

export function DateField({ value, onChange, error, minimumISO, accessibilityLabel = 'Tarih seç' }: Props) {
  const p = useTheme();
  const insets = useSafeAreaInsets();
  const current = toDate(trToIso(value) ?? toISO(new Date()));
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(current);
  const today = new Date();
  const minimumDate = minimumISO ? toDate(minimumISO) : undefined;

  function pick(d: Date) {
    onChange(isoToTr(toISO(d)));
    Haptics.selectionAsync().catch(() => {});
  }

  function openPicker() {
    if (Platform.OS === 'android') {
      DateTimePickerAndroid.open({
        value: current,
        mode: 'date',
        maximumDate: today,
        minimumDate,
        onChange: (e: DateTimePickerEvent, d?: Date) => {
          if (e.type === 'set' && d) pick(d);
        },
      });
      return;
    }
    setDraft(current);
    setOpen(true);
  }

  return (
    <View>
      <Pressable onPress={openPicker} accessibilityRole="button" accessibilityLabel={`${accessibilityLabel}: ${value}`}>
        {({ pressed }) => (
          <View
            style={[
              styles.field,
              { backgroundColor: p.inputFill, borderColor: error ? p.down : p.glassBorder, opacity: pressed ? 0.8 : 1 },
            ]}
          >
            <Ionicons name="calendar-outline" size={20} color={p.textMuted} />
            <AppText variant="bodyMedium" style={styles.flex}>
              {value}
            </AppText>
            <Ionicons name="chevron-down" size={18} color={p.textFaint} />
          </View>
        )}
      </Pressable>
      {error ? (
        <AppText variant="caption" color="down" style={styles.error}>
          {error}
        </AppText>
      ) : null}

      {/* iOS: alttan açılan takvim paneli */}
      <Modal visible={open} transparent animationType="slide" onRequestClose={() => setOpen(false)}>
        <Pressable style={styles.backdrop} onPress={() => setOpen(false)} accessibilityLabel="Kapat" />
        <View style={[styles.sheet, { paddingBottom: Math.max(insets.bottom, 16) }]}>
          <GlassCard strong padding={12} radius={radius.lg}>
            <DateTimePicker
              value={draft}
              mode="date"
              display="inline"
              locale="tr-TR"
              maximumDate={today}
              minimumDate={minimumDate}
              themeVariant={p.name === 'dark' ? 'dark' : 'light'}
              accentColor={p.accent}
              onChange={(_e: DateTimePickerEvent, d?: Date) => d && setDraft(d)}
            />
            <View style={styles.actions}>
              <Button variant="ghost" title="Vazgeç" onPress={() => setOpen(false)} style={styles.flex} />
              <Button
                title="Tamam"
                icon="checkmark"
                style={styles.flex}
                onPress={() => {
                  pick(draft);
                  setOpen(false);
                }}
              />
            </View>
          </GlassCard>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  field: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    height: 54,
    paddingHorizontal: 16,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth * 2,
  },
  error: { marginTop: 6, marginLeft: 4 },
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.35)' },
  sheet: { position: 'absolute', left: 12, right: 12, bottom: 0 },
  actions: { flexDirection: 'row', gap: 10, marginTop: 8 },
});
