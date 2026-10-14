// Cihazda kalıcı tutulan uygulama ayarları (tema, yasal uyarı onayı, risk profili, bildirim tercihleri).
import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

export type ThemePreference = 'system' | 'light' | 'dark';
import type { QuietHours, RiskProfile } from '@/api/types';
export type { RiskProfile };

interface SettingsState {
  themePreference: ThemePreference;
  /** Kullanıcının onayladığı yasal uyarı sürümü; metin değişirse yeniden onay istenir */
  disclaimerVersion: number | null;
  riskProfile: RiskProfile | null;
  budget: number | null;
  /** Model sinyali bildirimleri açık mı (izin verildiyse) */
  notificationsEnabled: boolean;
  /** Bu saatler arasında bildirim gönderilmez (sunucu da uygular) */
  quietHours: QuietHours | null;
  dailyPushLimit: number;
  /** Son alınan Expo push token'ı (yoksa null; EAS projesi kurulunca dolar) */
  pushToken: string | null;
  /** AsyncStorage'dan okuma bitti mi? Bitmeden yönlendirme yapılmaz. */
  hydrated: boolean;

  setThemePreference: (p: ThemePreference) => void;
  acceptDisclaimer: (version: number) => void;
  setRiskProfile: (p: RiskProfile, budget: number | null) => void;
  resetOnboarding: () => void;
  resetRiskProfile: () => void;
  setNotifications: (patch: Partial<Pick<SettingsState, 'notificationsEnabled' | 'quietHours' | 'dailyPushLimit' | 'pushToken'>>) => void;
}

export const useSettings = create<SettingsState>()(
  persist(
    (set) => ({
      themePreference: 'system',
      disclaimerVersion: null,
      riskProfile: null,
      budget: null,
      notificationsEnabled: false,
      quietHours: { start: '22:30', end: '08:00' },
      dailyPushLimit: 5,
      pushToken: null,
      hydrated: false,

      setThemePreference: (themePreference) => set({ themePreference }),
      acceptDisclaimer: (version) => set({ disclaimerVersion: version }),
      setRiskProfile: (riskProfile, budget) => set({ riskProfile, budget }),
      resetOnboarding: () => set({ disclaimerVersion: null, riskProfile: null, budget: null }),
      resetRiskProfile: () => set({ riskProfile: null }),
      setNotifications: (patch) => set(patch),
    }),
    {
      name: 'fon-takip-settings',
      storage: createJSONStorage(() => AsyncStorage),
      partialize: ({ hydrated: _hydrated, ...rest }) => rest,
      onRehydrateStorage: () => () => {
        useSettings.setState({ hydrated: true });
      },
    },
  ),
);
