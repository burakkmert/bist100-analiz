import { Stack } from 'expo-router';

import { DISCLAIMER_VERSION } from '@/lib/legal';
import { useSettings } from '@/store/settings';

export default function OnboardingLayout() {
  const accepted = useSettings((s) => s.disclaimerVersion === DISCLAIMER_VERSION);
  return (
    <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: 'transparent' }, animation: 'none' }}>
      {/* Uyarı onaylanınca bu ekran kapanır ve risk anketine geçilir */}
      <Stack.Protected guard={!accepted}>
        <Stack.Screen name="disclaimer" />
      </Stack.Protected>
      <Stack.Screen name="risk-profile" />
    </Stack>
  );
}
