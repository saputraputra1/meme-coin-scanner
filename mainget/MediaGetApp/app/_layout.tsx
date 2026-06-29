import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { useStore } from '../store';

export default function RootLayout() {
  const loadSettings = useStore((s) => s.loadSettings);
  const darkMode = useStore((s) => s.settings.darkMode);

  useEffect(() => { loadSettings(); }, []);

  return (
    <>
      <StatusBar style={darkMode ? 'light' : 'dark'} />
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="result/[id]" options={{ animation: 'slide_from_right' }} />
        <Stack.Screen name="player/[id]" options={{ animation: 'slide_from_bottom' }} />
      </Stack>
    </>
  );
}
