// Şifre sıfırlama: e-postaya sıfırlama bağlantısı gönderir.
import { router } from 'expo-router';
import { useState } from 'react';

import { AuthShell } from '@/components/AuthShell';
import { AppText, Button, TextField } from '@/components/ui';
import { isEmail } from '@/lib/validate';
import { useAuth } from '@/store/auth';

export default function ForgotPassword() {
  const resetPassword = useAuth((s) => s.resetPassword);
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  async function submit() {
    setError(null);
    if (!isEmail(email)) return setError('Geçerli bir e-posta adresi girin.');
    setBusy(true);
    try {
      await resetPassword(email.trim());
      setSent(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Bir hata oluştu.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell title="Şifre sıfırlama" subtitle="Kayıtlı e-posta adresinize bir bağlantı göndereceğiz">
      {sent ? (
        <AppText color="up">Bağlantı gönderildi. Gelen kutunuzu (ve gereksiz klasörünü) kontrol edin.</AppText>
      ) : (
        <>
          <TextField
            label="E-posta"
            icon="mail-outline"
            placeholder="ornek@eposta.com"
            autoCapitalize="none"
            keyboardType="email-address"
            value={email}
            onChangeText={setEmail}
            onSubmitEditing={submit}
          />
          {error ? (
            <AppText variant="caption" color="down">
              {error}
            </AppText>
          ) : null}
          <Button title="Bağlantı gönder" onPress={submit} loading={busy} />
        </>
      )}
      <Button variant="ghost" title="Girişe dön" onPress={() => router.back()} />
    </AuthShell>
  );
}
