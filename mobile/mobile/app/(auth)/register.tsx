// Kayıt ekranı
import { router } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { AuthShell } from '@/components/AuthShell';
import { AppText, Button, GlassIcon, TextField } from '@/components/ui';
import { isEmail, MIN_PASSWORD } from '@/lib/validate';
import { useAuth } from '@/store/auth';

export default function Register() {
  const signUp = useAuth((s) => s.signUp);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [password2, setPassword2] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  async function submit() {
    setError(null);
    if (!isEmail(email)) return setError('Geçerli bir e-posta adresi girin.');
    if (password.length < MIN_PASSWORD) return setError(`Şifre en az ${MIN_PASSWORD} karakter olmalı.`);
    if (password !== password2) return setError('Şifreler eşleşmiyor.');
    setBusy(true);
    try {
      const { needsConfirmation } = await signUp(email.trim(), password);
      if (needsConfirmation) setSent(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Bir hata oluştu.');
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <AuthShell title="E-postanızı kontrol edin">
        <View style={styles.center}>
          <GlassIcon name="mail-unread-outline" size={56} tone="up" />
          <AppText color="textMuted" style={styles.text}>
            {email} adresine bir doğrulama bağlantısı gönderdik. Bağlantıya dokunduktan sonra giriş yapabilirsiniz.
          </AppText>
        </View>
        <Button title="Girişe dön" onPress={() => router.replace('/login')} />
      </AuthShell>
    );
  }

  return (
    <AuthShell title="Hesap oluştur" subtitle="Portföyünüz ve izleme listeniz hesabınıza kaydedilir">
      <TextField
        label="E-posta"
        icon="mail-outline"
        placeholder="ornek@eposta.com"
        autoCapitalize="none"
        autoComplete="email"
        keyboardType="email-address"
        value={email}
        onChangeText={setEmail}
      />
      <TextField
        label="Şifre"
        icon="lock-closed-outline"
        placeholder={`En az ${MIN_PASSWORD} karakter`}
        password
        autoComplete="new-password"
        textContentType="newPassword"
        value={password}
        onChangeText={setPassword}
      />
      <TextField
        label="Şifre (tekrar)"
        icon="lock-closed-outline"
        password
        autoComplete="new-password"
        value={password2}
        onChangeText={setPassword2}
        onSubmitEditing={submit}
      />
      {error ? (
        <AppText variant="caption" color="down">
          {error}
        </AppText>
      ) : null}
      <Button title="Kayıt ol" onPress={submit} loading={busy} />
      <Button variant="ghost" title="Zaten hesabım var" onPress={() => router.back()} />
    </AuthShell>
  );
}

const styles = StyleSheet.create({
  center: { alignItems: 'center', gap: 12 },
  text: { textAlign: 'center' },
});
