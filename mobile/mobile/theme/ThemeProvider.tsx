// Tema sağlayıcısı: sistem / açık / koyu tercihine göre doğru paleti verir.
import { createContext, useContext, useMemo, type ReactNode } from 'react';
import { useColorScheme } from 'react-native';

import { useSettings } from '@/store/settings';
import { dark, light, type Palette } from './colors';

const ThemeContext = createContext<Palette>(dark);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const system = useColorScheme();
  const preference = useSettings((s) => s.themePreference);

  const palette = useMemo(() => {
    const resolved = preference === 'system' ? (system ?? 'dark') : preference;
    return resolved === 'light' ? light : dark;
  }, [preference, system]);

  return <ThemeContext.Provider value={palette}>{children}</ThemeContext.Provider>;
}

export const useTheme = () => useContext(ThemeContext);
