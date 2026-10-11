import { Tabs } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { GlassTabBar } from '@/components/GlassTabBar';

export default function TabsLayout() {
  return (
    <View style={styles.flex}>
      <Tabs
        tabBar={(props) => <GlassTabBar {...props} />}
        screenOptions={{ headerShown: false, sceneStyle: { backgroundColor: 'transparent' } }}
      >
        <Tabs.Screen name="index" />
        <Tabs.Screen name="markets" />
        <Tabs.Screen name="portfolio" />
        <Tabs.Screen name="settings" />
      </Tabs>
    </View>
  );
}

const styles = StyleSheet.create({ flex: { flex: 1 } });
