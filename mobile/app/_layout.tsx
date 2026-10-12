// Kök düzen: yazı tipleri, sağlayıcılar, hareketli arka plan ve yönlendirme korumaları.
import {
  Inter_400Regular,
  Inter_500Medium,
  Inter_600SemiBold,
  Inter_700Bold,
  useFonts,
} from '@expo-google-fonts/inter';
import { DarkTheme, DefaultTheme, ThemeProvider as NavThemeProvider } from 'expo-router/react-navigation';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Stack, usePathname } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import * as SystemUI from 'expo-system-ui';
import { useEffect, useMemo } from 'react';
import { StyleSheet, View } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';

import { AIBubble } from '@/components/ai/AIBubble';
import { AnimatedBackground } from '@/components/AnimatedBackground';
import { ThemeFadeOverlay } from '@/components/ThemeFadeOverlay';
import { DISCLAIMER_VERSION } from '@/lib/legal';
import { useAuth } from '@/store/auth';
import { useSettings } from '@/store/settings';
import { ThemeProvider, useTheme } from '@/theme/ThemeProvider';

SplashScreen.preventAutoHideAsync().catch(() => {});

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 60_000, retry: 1 } },
});

export default function RootLayout() {
  return (
    <GestureHandlerRootView style={styles.flex}>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <RootNavigator />
        </ThemeProvider>
      </QueryClientProvider>
    </GestureHandlerRootView>
  );
}

function RootNavigator() {
  const p = useTheme();
  const [fontsLoaded] = useFonts({ Inter_400Regular, Inter_500Medium, Inter_600SemiBold, Inter_700Bold });

  const hydrated = useSettings((s) => s.hydrated);
  const disclaimerVersion = useSettings((s) => s.disclaimerVersion);
  const riskProfile = useSettings((s) => s.riskProfile);
  const user = useAuth((s) => s.user);
  const authReady = useAuth((s) => s.ready);
  const pathname = usePathname();

  useEffect(() => useAuth.getState().init(), []);

  const ready = fontsLoaded && hydrated && authReady;
  useEffect(() => {
    if (ready) SplashScreen.hideAsync().catch(() => {});
  }, [ready]);

  // Pencerenin kök rengi: ekran geçişlerinde beyaz parlama olmasın
  useEffect(() => {
    SystemUI.setBackgroundColorAsync(p.bgGradient[0]).catch(() => {});
  }, [p]);

  // React Navigation arka planı şeffaf olmalı ki hareketli zemin görünsün
  const navTheme = useMemo(() => {
    const base = p.name === 'dark' ? DarkTheme : DefaultTheme;
    return { ...base, colors: { ...base.colors, background: 'transparent', primary: p.accent, text: p.text } };
  }, [p]);

  if (!ready) return null;

  const signedIn = !!user;
  const onboarded = disclaimerVersion === DISCLAIMER_VERSION && !!riskProfile;

  return (
    <NavThemeProvider value={navTheme}>
      <View style={[styles.flex, { backgroundColor: p.bgGradient[0] }]}>
        <AnimatedBackground />
        <StatusBar style={p.name === 'dark' ? 'light' : 'dark'} />
        <Stack
          screenOptions={{
            headerShown: false,
            contentStyle: { backgroundColor: 'transparent' },
            // Ekranlar saydam (arkada hareketli zemin var); yerel kaydırma/solma geçişinde
            // iki ekranın yazıları üst üste görünüyordu. Geçişi ekranların kendi giriş animasyonları yapar.
            animation: 'none',
          }}
        >
          {/* Giriş yapılmamışsa yalnızca giriş ekranları */}
          <Stack.Protected guard={!signedIn}>
            <Stack.Screen name="(auth)" />
          </Stack.Protected>

          {/* Giriş yapılmış ama yasal uyarı / risk anketi bitmemiş */}
          <Stack.Protected guard={signedIn && !onboarded}>
            <Stack.Screen name="onboarding" />
          </Stack.Protected>

          {/* Asıl uygulama */}
          <Stack.Protected guard={signedIn && onboarded}>
            <Stack.Screen name="(tabs)" />
            {/* Detay ekranının kendi arka planı var → sağdan kayarak açılabilir, kaydırarak geri dönülebilir */}
            <Stack.Screen name="asset/[code]" options={{ animation: 'slide_from_right', gestureEnabled: true }} />
            <Stack.Screen name="assistant" options={{ presentation: 'modal', animation: 'slide_from_bottom' }} />
            <Stack.Screen name="chart-read" options={{ presentation: 'modal', animation: 'slide_from_bottom' }} />
            <Stack.Screen name="position/new" options={{ presentation: 'modal', animation: 'slide_from_bottom' }} />
            <Stack.Screen name="position/[id]" options={{ presentation: 'modal', animation: 'slide_from_bottom' }} />
          </Stack.Protected>

          <Stack.Screen name="auth/callback" />
        </Stack>
        {/* Yapay zekâ balonu: uygulamanın her ekranında (asistanın kendisi hariç) */}
        {signedIn && onboarded && pathname !== '/assistant' ? <AIBubble /> : null}
        <ThemeFadeOverlay />
      </View>
    </NavThemeProvider>
  );
}

const styles = StyleSheet.create({ flex: { flex: 1 } });
