// Giriş ekranı: e-posta/şifre, Google, Apple; Supabase ayarlı değilse demo mod.
import { Ionicons } from '@expo/vector-icons';
import { Link } from 'expo-router';
import { useState } from 'react';
import { Platform, Pressable, StyleSheet, View } from 'react-native';

import { AuthShell } from '@/components/AuthShell';
import { AppText, Button, TextField } from '@/components/ui';
import { isDemoMode } from '@/lib/supabase';
import { isEmail } from '@/lib/validate';
import { useAuth } from '@/store/auth';
import { useTheme } from '@/theme/ThemeProvider';

export default function Login() {
  const p = useTheme();
  const { signIn, signInWithProvider, signInDemo } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState<null | 'email' | 'google' | 'apple'>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(kind: 'email' | 'google' | 'apple') {
    setError(null);
    if (kind === 'email') {
      if (!isEmail(email)) return setError('Geçerli bir e-posta adresi girin.');
      if (!password) return setError('Şifrenizi girin.');
    }
    setBusy(kind);
    try {
      if (kind === 'email') await signIn(email.trim(), password);
      else await signInWithProvider(kind);
      // Başarılı girişte kök düzendeki koruma otomatik yönlendirir.
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Bir hata oluştu.');
    } finally {
      setBusy(null);
    }
  }

  return (
    <AuthShell
      title="Fon Takip"
      subtitle="BIST hisseleri ve TEFAS fonları için model sinyalleri"
      footer={
        <View style={styles.footer}>
          <AppText color="textMuted">Hesabınız yok mu?</AppText>
          <Link href="/register" asChild>
            <Pressable hitSlop={8}>
              <AppText color="accent" variant="bodyMedium">
                Kayıt olun
              </AppText>
            </Pressable>
          </Link>
        </View>
      }
    >
      {isDemoMode ? (
        <View style={[styles.demo, { backgroundColor: p.accentSoft }]}>
          <Ionicons name="flask-outline" size={16} color={p.accent} />
          <AppText variant="caption" color="textMuted" style={styles.flex}>
            Supabase henüz ayarlanmadı. Arayüzü denemek için demo modla devam edebilirsiniz.
          </AppText>
        </View>
      ) : null}

      <TextField
        label="E-posta"
        icon="mail-outline"
        placeholder="ornek@eposta.com"
        autoCapitalize="none"
        autoComplete="email"
        keyboardType="email-address"
        textContentType="emailAddress"
        value={email}
        onChangeText={setEmail}
      />
      <TextField
        label="Şifre"
        icon="lock-closed-outline"
        placeholder="••••••••"
        password
        autoComplete="current-password"
        textContentType="password"
        value={password}
        onChangeText={setPassword}
        onSubmitEditing={() => run('email')}
        returnKeyType="go"
      />

      <Link href="/forgot-password" asChild>
        <Pressable hitSlop={8} style={styles.forgot}>
          <AppText variant="caption" color="accent">
            Şifremi unuttum
          </AppText>
        </Pressable>
      </Link>

      {error ? (
        <AppText variant="caption" color="down" accessibilityLiveRegion="polite">
          {error}
        </AppText>
      ) : null}

      <Button title="Giriş yap" onPress={() => run('email')} loading={busy === 'email'} disabled={!!busy} />

      <View style={styles.divider}>
        <View style={[styles.line, { backgroundColor: p.separator }]} />
        <AppText variant="caption" color="textFaint">
          veya
        </AppText>
        <View style={[styles.line, { backgroundColor: p.separator }]} />
      </View>

      <Button
        variant="glass"
        title="Google ile devam et"
        icon="logo-google"
        onPress={() => run('google')}
        loading={busy === 'google'}
        disabled={!!busy}
      />
      {Platform.OS === 'ios' ? (
        <Button
          variant="glass"
          title="Apple ile devam et"
          icon="logo-apple"
          onPress={() => run('apple')}
          loading={busy === 'apple'}
          disabled={!!busy}
        />
      ) : null}

      {isDemoMode ? <Button variant="ghost" title="Demo modla devam et" icon="arrow-forward" onPress={signInDemo} /> : null}
    </AuthShell>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  demo: { flexDirection: 'row', gap: 8, padding: 10, borderRadius: 12, alignItems: 'flex-start' },
  forgot: { alignSelf: 'flex-end', marginTop: -4 },
  divider: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  line: { flex: 1, height: StyleSheet.hairlineWidth * 2 },
  footer: { flexDirection: 'row', justifyContent: 'center', gap: 6 },
});
