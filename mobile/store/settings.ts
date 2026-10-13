// Cihazda kalıcı tutulan uygulama ayarları (tema tercihi, yasal uyarı onayı, risk profili).
import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

export type ThemePreference = 'system' | 'light' | 'dark';
import type { RiskProfile } from '@/api/types';
export type { RiskProfile };

interface SettingsState {
  themePreference: ThemePreference;
  /** Kullanıcının onayladığı yasal uyarı sürümü; metin değişirse yeniden onay istenir */
  disclaimerVersion: number | null;
  riskProfile: RiskProfile | null;
  budget: number | null;
  /** AsyncStorage'dan okuma bitti mi? Bitmeden yönlendirme yapılmaz. */
  hydrated: boolean;

  setThemePreference: (p: ThemePreference) => void;
  acceptDisclaimer: (version: number) => void;
  setRiskProfile: (p: RiskProfile, budget: number | null) => void;
  resetOnboarding: () => void;
  resetRiskProfile: () => void;
}

export const useSettings = create<SettingsState>()(
  persist(
    (set) => ({
      themePreference: 'system',
      disclaimerVersion: null,
      riskProfile: null,
      budget: null,
      hydrated: false,

      setThemePreference: (themePreference) => set({ themePreference }),
      acceptDisclaimer: (version) => set({ disclaimerVersion: version }),
      setRiskProfile: (riskProfile, budget) => set({ riskProfile, budget }),
      resetOnboarding: () => set({ disclaimerVersion: null, riskProfile: null, budget: null }),
      resetRiskProfile: () => set({ riskProfile: null }),
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
