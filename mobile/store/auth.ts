// Oturum durumu. Gerçek modda Supabase, demo modda sahte kullanıcı.
import * as Linking from 'expo-linking';
import * as WebBrowser from 'expo-web-browser';
import { create } from 'zustand';

import { isDemoMode, supabase } from '@/lib/supabase';

WebBrowser.maybeCompleteAuthSession();

export interface AppUser {
  id: string;
  email: string | null;
}

interface AuthState {
  user: AppUser | null;
  accessToken: string | null;
  ready: boolean; // ilk oturum kontrolü bitti mi
  init: () => () => void;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string) => Promise<{ needsConfirmation: boolean }>;
  resetPassword: (email: string) => Promise<void>;
  signInWithProvider: (provider: 'google' | 'apple') => Promise<void>;
  signInDemo: () => void;
  signOut: () => Promise<void>;
}

const DEMO_USER: AppUser = { id: 'demo-user', email: 'demo@fontakip.app' };

/** Supabase hata mesajlarını Türkçeleştirir */
function tr(message: string): string {
  const m = message.toLowerCase();
  if (m.includes('invalid login')) return 'E-posta veya şifre hatalı.';
  if (m.includes('email not confirmed')) return 'E-posta adresiniz henüz doğrulanmamış. Gelen kutunuzu kontrol edin.';
  if (m.includes('already registered')) return 'Bu e-posta ile zaten bir hesap var.';
  if (m.includes('password should be')) return 'Şifre en az 6 karakter olmalı.';
  if (m.includes('rate limit')) return 'Çok fazla deneme yapıldı. Biraz sonra tekrar deneyin.';
  if (m.includes('network')) return 'Bağlantı kurulamadı. İnternetinizi kontrol edin.';
  return message;
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  accessToken: null,
  ready: false,

  init: () => {
    if (!supabase) {
      set({ ready: true });
      return () => {};
    }
    supabase.auth.getSession().then(({ data }) => {
      const s = data.session;
      set({
        ready: true,
        user: s ? { id: s.user.id, email: s.user.email ?? null } : null,
        accessToken: s?.access_token ?? null,
      });
    });
    const { data } = supabase.auth.onAuthStateChange((_event, s) => {
      set({
        user: s ? { id: s.user.id, email: s.user.email ?? null } : null,
        accessToken: s?.access_token ?? null,
      });
    });
    return () => data.subscription.unsubscribe();
  },

  signIn: async (email, password) => {
    if (!supabase) throw new Error('Supabase ayarlı değil. Demo modla devam edebilirsiniz.');
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw new Error(tr(error.message));
  },

  signUp: async (email, password) => {
    if (!supabase) throw new Error('Supabase ayarlı değil. Demo modla devam edebilirsiniz.');
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: { emailRedirectTo: Linking.createURL('auth/callback') },
    });
    if (error) throw new Error(tr(error.message));
    return { needsConfirmation: !data.session };
  },

  resetPassword: async (email) => {
    if (!supabase) throw new Error('Supabase ayarlı değil.');
    const { error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: Linking.createURL('auth/callback'),
    });
    if (error) throw new Error(tr(error.message));
  },

  signInWithProvider: async (provider) => {
    if (!supabase) throw new Error('Supabase ayarlı değil. Demo modla devam edebilirsiniz.');
    const redirectTo = Linking.createURL('auth/callback');
    const { data, error } = await supabase.auth.signInWithOAuth({
      provider,
      options: { redirectTo, skipBrowserRedirect: true },
    });
    if (error || !data.url) throw new Error(tr(error?.message ?? 'Giriş başlatılamadı.'));

    const result = await WebBrowser.openAuthSessionAsync(data.url, redirectTo);
    if (result.type !== 'success') return; // kullanıcı vazgeçti

    const { queryParams } = Linking.parse(result.url);
    const code = typeof queryParams?.code === 'string' ? queryParams.code : null;
    if (!code) throw new Error('Giriş tamamlanamadı.');
    const { error: exErr } = await supabase.auth.exchangeCodeForSession(code);
    if (exErr) throw new Error(tr(exErr.message));
  },

  signInDemo: () => set({ user: DEMO_USER, accessToken: null, ready: true }),

  signOut: async () => {
    if (supabase && !isDemoMode) await supabase.auth.signOut();
    set({ user: null, accessToken: null });
  },
}));
