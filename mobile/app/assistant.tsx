// Yapay zekâ asistanı: soru sor, ekran görüntüsü / fotoğraf / grafik gönder, fikir alışverişi yap.
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import * as ImagePicker from 'expo-image-picker';
import { LinearGradient } from 'expo-linear-gradient';
import { router } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import {
  ActionSheetIOS,
  Alert,
  Image,
  Keyboard,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';
import Animated, {
  FadeIn,
  FadeInDown,
  FadeInUp,
  useAnimatedKeyboard,
  useAnimatedStyle,
  useSharedValue,
  withDelay,
  withRepeat,
  withSequence,
  withTiming,
} from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AnimatedBackground } from '@/components/AnimatedBackground';
import { AppText, GlassCard, GlassIcon } from '@/components/ui';
import { useAssistant, type ChatMessage } from '@/store/assistant';
import { font, radius } from '@/theme/colors';
import { useTheme } from '@/theme/ThemeProvider';

const SUGGESTIONS = [
  { icon: 'scan-outline', text: 'Az önceki ekranı açıkla', useScreen: true },
  { icon: 'analytics-outline', text: 'Bu grafiği yorumlar mısın?', useScreen: true },
  { icon: 'help-circle-outline', text: 'RSI nedir?' },
  { icon: 'shield-half-outline', text: 'Güven skoru ne anlama geliyor?' },
] as const;

export default function Assistant() {
  const p = useTheme();
  const insets = useSafeAreaInsets();
  const { messages, loading, lastScreen, send, clear, context } = useAssistant();
  const [text, setText] = useState('');
  const [attachment, setAttachment] = useState<string | null>(null);
  const scroll = useRef<ScrollView>(null);

  // Yeni mesajda ve cevap akarken (metin uzadıkça) en alta kaydır
  const lastLen = messages[messages.length - 1]?.text.length ?? 0;
  useEffect(() => {
    const t = setTimeout(() => scroll.current?.scrollToEnd({ animated: true }), 60);
    return () => clearTimeout(t);
  }, [messages.length, loading, Math.floor(lastLen / 40)]);

  function submit(msg = text, image = attachment) {
    if (!msg.trim() && !image) return;
    Haptics.selectionAsync().catch(() => {});
    send(msg, image);
    Keyboard.dismiss();
    setText('');
    setAttachment(null);
  }

  async function pickFromLibrary() {
    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      quality: 0.6,
      base64: true,
      allowsEditing: false,
    });
    if (!res.canceled && res.assets[0]) setAttachment(toDataUri(res.assets[0]));
  }

  async function takePhoto() {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) {
      Alert.alert('Kamera izni gerekli', 'Fotoğraf çekmek için Ayarlar’dan kamera iznini açabilirsiniz.');
      return;
    }
    const res = await ImagePicker.launchCameraAsync({ quality: 0.6, base64: true });
    if (!res.canceled && res.assets[0]) setAttachment(toDataUri(res.assets[0]));
  }

  function openAttachMenu() {
    const options = [
      ...(lastScreen ? [{ label: 'Az önceki ekran', run: () => setAttachment(lastScreen) }] : []),
      { label: 'Fotoğraflardan seç (ekran görüntüsü, grafik…)', run: pickFromLibrary },
      { label: 'Fotoğraf çek', run: takePhoto },
    ];
    if (Platform.OS === 'ios') {
      ActionSheetIOS.showActionSheetWithOptions(
        { options: [...options.map((o) => o.label), 'Vazgeç'], cancelButtonIndex: options.length },
        (i) => options[i]?.run(),
      );
    } else {
      Alert.alert('Görsel ekle', undefined, [
        ...options.map((o) => ({ text: o.label, onPress: o.run })),
        { text: 'Vazgeç', style: 'cancel' as const },
      ]);
    }
  }

  const empty = messages.length === 0;

  // Klavye yüksekliği (modal sayfanın altı ekranın altına hizalı olduğundan doğrudan kullanılabilir)
  const keyboard = useAnimatedKeyboard();
  const bottomInset = Math.max(insets.bottom, 10);
  const keyboardPad = useAnimatedStyle(() => ({ paddingBottom: keyboard.height.value }));
  // Klavye açıkken alttaki güvenli alan boşluğu gereksiz; kapalıyken geri gelir
  const composerPad = useAnimatedStyle(() => ({
    paddingBottom: keyboard.height.value > 0 ? 8 : bottomInset,
  }));

  return (
    <View style={styles.flex}>
      <AnimatedBackground />

      {/* Başlık */}
      <View style={[styles.header, { paddingTop: insets.top + 10 }]}>
        <View style={styles.headerTitle}>
          <GlassIcon name="sparkles" size={38} />
          <View>
            <AppText variant="heading">Asistan</AppText>
            <AppText variant="caption" color="textMuted">
              {loading ? 'Yazıyor…' : context?.code ? `${context.code} ekranından açıldı` : 'Soru sorun, görsel gönderin'}
            </AppText>
          </View>
        </View>
        <View style={styles.headerActions}>
          {!empty ? (
            <HeaderButton icon="trash-outline" label="Sohbeti temizle" onPress={clear} />
          ) : null}
          <HeaderButton icon="close" label="Kapat" onPress={() => router.back()} />
        </View>
      </View>

      {/* Klavye: yüksekliği UI iş parçacığında izlenir; içerik klavyeyle birlikte kayar,
          parmakla aşağı sürüklerken de klavyeyi takip eder. */}
      <Animated.View style={[styles.flex, keyboardPad]}>
        <ScrollView
          ref={scroll}
          style={styles.flex}
          contentContainerStyle={styles.list}
          keyboardShouldPersistTaps="handled"
          alwaysBounceVertical // içerik kısa olsa da sürüklenebilsin → klavye inebilsin
          keyboardDismissMode={Platform.OS === 'ios' ? 'interactive' : 'on-drag'}
          showsVerticalScrollIndicator={false}
        >
          {empty ? (
            <Animated.View entering={FadeInDown.duration(450)} style={styles.welcome}>
              <AppText variant="title" style={styles.center}>
                Size nasıl yardımcı olabilirim?
              </AppText>
              <AppText color="textMuted" style={styles.center}>
                Ekranda anlamadığınız bir terimi sorun, grafiğin ekran görüntüsünü gönderip yorumlatın ya da bir fikri
                birlikte tartışalım.
              </AppText>

              {lastScreen ? (
                <GlassCard padding={10} style={styles.screenCard}>
                  <View style={styles.row}>
                    <Image source={{ uri: lastScreen }} style={styles.screenThumb} />
                    <View style={styles.flex}>
                      <AppText variant="bodyMedium">Az önceki ekranınız hazır</AppText>
                      <AppText variant="caption" color="textMuted">
                        Aşağıdaki önerilerden biri bu görüntüyü otomatik ekler.
                      </AppText>
                    </View>
                  </View>
                </GlassCard>
              ) : null}

              <View style={styles.suggestions}>
                {context?.code ? (
                  <Animated.View entering={FadeInUp.duration(400)}>
                    <Pressable
                      onPress={() => submit(`${context.code} için bu sinyal neden geldi?`, null)}
                      style={[styles.chip, { backgroundColor: p.accentSoft, borderColor: p.accent }]}
                    >
                      <Ionicons name="bulb-outline" size={16} color={p.accent} />
                      <AppText variant="bodyMedium">{context.code} için bu sinyal neden geldi?</AppText>
                    </Pressable>
                  </Animated.View>
                ) : null}
                {SUGGESTIONS.filter((s) => !('useScreen' in s) || lastScreen).map((s, i) => (
                  <Animated.View key={s.text} entering={FadeInUp.delay(100 + i * 60).duration(400)}>
                    <Pressable
                      onPress={() => submit(s.text, 'useScreen' in s ? lastScreen : null)}
                      style={[styles.chip, { backgroundColor: p.glassFillStrong, borderColor: p.glassBorder }]}
                    >
                      <Ionicons name={s.icon} size={16} color={p.accent} />
                      <AppText variant="bodyMedium">{s.text}</AppText>
                    </Pressable>
                  </Animated.View>
                ))}
              </View>
            </Animated.View>
          ) : (
            messages.map((m) => <Bubble key={m.id} message={m} />)
          )}

          {loading && !messages.some((m) => m.streaming) ? <TypingIndicator /> : null}

          {!empty ? (
            <AppText variant="caption" color="textFaint" style={[styles.center, styles.note]}>
              Asistanın yorumları model çıktısıdır, yatırım tavsiyesi değildir. Hata yapabilir.
            </AppText>
          ) : null}
        </ScrollView>

        {/* Giriş çubuğu */}
        <Animated.View style={[styles.composerWrap, composerPad]}>
          {attachment ? (
            <Animated.View entering={FadeIn.duration(200)} style={styles.attachRow}>
              <View>
                <Image source={{ uri: attachment }} style={styles.attachThumb} />
                <Pressable
                  onPress={() => setAttachment(null)}
                  style={[styles.attachRemove, { backgroundColor: p.text }]}
                  accessibilityLabel="Görseli kaldır"
                  hitSlop={8}
                >
                  <Ionicons name="close" size={12} color={p.bgGradient[0]} />
                </Pressable>
              </View>
              <AppText variant="caption" color="textMuted">
                Görsel eklendi · sorunuzu yazın
              </AppText>
            </Animated.View>
          ) : null}

          <GlassCard radius={radius.xl} padding={6} strong>
            <View style={styles.composer}>
              <Pressable onPress={openAttachMenu} style={styles.iconBtn} accessibilityLabel="Görsel ekle" hitSlop={6}>
                <Ionicons name="attach" size={22} color={p.textMuted} />
              </Pressable>
              <TextInput
                value={text}
                onChangeText={setText}
                placeholder="Bir şey sorun…"
                placeholderTextColor={p.textFaint}
                selectionColor={p.accent}
                multiline
                style={[styles.input, { color: p.text }]}
                maxLength={2000}
              />
              <Pressable
                onPress={() => submit()}
                disabled={loading || (!text.trim() && !attachment)}
                accessibilityLabel="Gönder"
                style={({ pressed }) => [
                  styles.send,
                  { opacity: loading || (!text.trim() && !attachment) ? 0.4 : pressed ? 0.8 : 1 },
                ]}
              >
                <LinearGradient
                  colors={p.name === 'dark' ? ['#8EBBFF', '#5A8DFF'] : ['#4A84FF', '#2459D6']}
                  style={StyleSheet.absoluteFill}
                />
                <Ionicons name="arrow-up" size={20} color={p.onAccent} />
              </Pressable>
            </View>
          </GlassCard>
        </Animated.View>
      </Animated.View>
    </View>
  );
}

function toDataUri(asset: ImagePicker.ImagePickerAsset) {
  if (asset.base64) return `data:${asset.mimeType ?? 'image/jpeg'};base64,${asset.base64}`;
  return asset.uri;
}

function HeaderButton({ icon, label, onPress }: { icon: 'close' | 'trash-outline'; label: string; onPress: () => void }) {
  const p = useTheme();
  return (
    <Pressable
      onPress={onPress}
      accessibilityLabel={label}
      hitSlop={6}
      style={[styles.headerBtn, { backgroundColor: p.glassFillStrong, borderColor: p.glassBorder }]}
    >
      <Ionicons name={icon} size={18} color={p.text} />
    </Pressable>
  );
}

function Bubble({ message }: { message: ChatMessage }) {
  const p = useTheme();
  const mine = message.role === 'user';
  return (
    <Animated.View entering={FadeInUp.duration(300)} style={[styles.msgRow, mine ? styles.right : styles.left]}>
      {!mine ? <GlassIcon name="sparkles" size={28} style={styles.avatar} /> : null}
      <View style={[styles.msgCol, mine && styles.msgColMine]}>
        {message.image ? <Image source={{ uri: message.image }} style={styles.msgImage} resizeMode="cover" /> : null}
        {mine ? (
          <View style={[styles.bubble, styles.bubbleMine]}>
            <LinearGradient
              colors={p.name === 'dark' ? ['#5A8DFF', '#3F6FE0'] : ['#4A84FF', '#2459D6']}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 1 }}
              style={StyleSheet.absoluteFill}
            />
            <AppText style={{ color: '#FFFFFF' }}>{message.text}</AppText>
          </View>
        ) : (
          <GlassCard padding={12} radius={18}>
            <AppText color={message.error ? 'down' : 'text'}>{message.text}</AppText>
          </GlassCard>
        )}
      </View>
    </Animated.View>
  );
}

function TypingIndicator() {
  return (
    <Animated.View entering={FadeIn.duration(200)} style={[styles.msgRow, styles.left]}>
      <GlassIcon name="sparkles" size={28} style={styles.avatar} />
      <GlassCard padding={14} radius={18}>
        <View style={styles.dots}>
          {[0, 1, 2].map((i) => (
            <Dot key={i} delay={i * 160} />
          ))}
        </View>
      </GlassCard>
    </Animated.View>
  );
}

function Dot({ delay }: { delay: number }) {
  const p = useTheme();
  const v = useSharedValue(0);
  useEffect(() => {
    v.value = withDelay(
      delay,
      withRepeat(withSequence(withTiming(1, { duration: 360 }), withTiming(0, { duration: 360 })), -1, false),
    );
  }, [delay, v]);
  const style = useAnimatedStyle(() => ({
    opacity: 0.35 + v.value * 0.65,
    transform: [{ translateY: -v.value * 4 }],
  }));
  return <Animated.View style={[styles.dot, { backgroundColor: p.textMuted }, style]} />;
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  center: { textAlign: 'center' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10 },

  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 18, paddingBottom: 10 },
  headerTitle: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  headerActions: { flexDirection: 'row', gap: 8 },
  headerBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: StyleSheet.hairlineWidth * 2,
  },

  list: { paddingHorizontal: 16, paddingTop: 8, paddingBottom: 16, gap: 12, flexGrow: 1 },
  welcome: { gap: 12, marginTop: 24 },
  screenCard: { marginTop: 4 },
  screenThumb: { width: 44, height: 78, borderRadius: 8 },
  suggestions: { gap: 8, marginTop: 6 },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth * 2,
  },

  msgRow: { flexDirection: 'row', gap: 8, alignItems: 'flex-end' },
  left: { justifyContent: 'flex-start', paddingRight: 40 },
  right: { justifyContent: 'flex-end', paddingLeft: 56 },
  avatar: { marginBottom: 2 },
  msgCol: { flexShrink: 1, gap: 6 },
  msgColMine: { alignItems: 'flex-end' },
  bubble: { paddingHorizontal: 14, paddingVertical: 10, borderRadius: 18, overflow: 'hidden' },
  bubbleMine: { borderBottomRightRadius: 6 },
  msgImage: { width: 170, height: 260, borderRadius: 14 },
  note: { marginTop: 8 },

  dots: { flexDirection: 'row', gap: 5, paddingHorizontal: 2 },
  dot: { width: 7, height: 7, borderRadius: 4 },

  composerWrap: { paddingHorizontal: 12, paddingTop: 6, gap: 8 },
  attachRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 6 },
  attachThumb: { width: 46, height: 64, borderRadius: 8 },
  attachRemove: {
    position: 'absolute',
    top: -6,
    right: -6,
    width: 20,
    height: 20,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  composer: { flexDirection: 'row', alignItems: 'flex-end', gap: 4 },
  iconBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  input: { flex: 1, fontFamily: font.regular, fontSize: 15, maxHeight: 120, paddingTop: 10, paddingBottom: 10 },
  send: { width: 40, height: 40, borderRadius: 20, overflow: 'hidden', alignItems: 'center', justifyContent: 'center' },
});
