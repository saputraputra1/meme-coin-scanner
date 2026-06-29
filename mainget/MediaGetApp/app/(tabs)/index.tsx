import { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  FlatList, KeyboardAvoidingView, Platform,
} from 'react-native';
import { router } from 'expo-router';
import { useStore } from '../../store';
import { detectPlatform, extractVideoId } from '../../lib/utils';

export default function HomeScreen() {
  const [url, setUrl] = useState('');
  const settings = useStore((s) => s.settings);
  const downloads = useStore((s) => s.downloads);

  const handleGo = () => {
    const trimmed = url.trim();
    if (!trimmed) return;
    const id = extractVideoId(trimmed) || encodeURIComponent(trimmed);
    router.push(`/result/${id}?url=${encodeURIComponent(trimmed)}`);
  };

  const recentDownloads = downloads.filter((d) => d.status === 'completed').slice(0, 5);

  return (
    <KeyboardAvoidingView
      style={[styles.container, { backgroundColor: settings.darkMode ? '#0a0a12' : '#f5f5f5' }]}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View style={styles.header}>
        <Text style={[styles.title, { color: settings.darkMode ? '#fff' : '#000' }]}>MediaGet</Text>
        <Text style={[styles.subtitle, { color: settings.darkMode ? '#888' : '#666' }]}>
          Download dari YouTube, TikTok, IG, FB
        </Text>
      </View>

      <View style={styles.inputContainer}>
        <TextInput
          style={[styles.input, {
            backgroundColor: settings.darkMode ? '#1a1a2e' : '#fff',
            color: settings.darkMode ? '#fff' : '#000',
            borderColor: settings.darkMode ? '#2a2a3e' : '#ddd',
          }]}
          placeholder="Tempel link YouTube/TikTok/IG/FB..."
          placeholderTextColor={settings.darkMode ? '#555' : '#999'}
          value={url}
          onChangeText={setUrl}
          autoCapitalize="none"
          autoCorrect={false}
          returnKeyType="go"
          onSubmitEditing={handleGo}
        />
        <TouchableOpacity style={styles.goButton} onPress={handleGo} activeOpacity={0.8}>
          <Text style={styles.goText}>GO</Text>
        </TouchableOpacity>
      </View>

      {url.length > 0 && (
        <View style={styles.preview}>
          <Text style={[styles.previewLabel, { color: settings.darkMode ? '#aaa' : '#666' }]}>
            {detectPlatform(url) !== 'unknown'
              ? `📺 ${detectPlatform(url).charAt(0).toUpperCase() + detectPlatform(url).slice(1)}`
              : '🌐 Link detected'}
          </Text>
        </View>
      )}

      {recentDownloads.length > 0 && (
        <View style={styles.section}>
          <Text style={[styles.sectionTitle, { color: settings.darkMode ? '#fff' : '#000' }]}>
            Recent Downloads
          </Text>
          {recentDownloads.map((item) => (
            <TouchableOpacity
              key={item.id}
              style={[styles.recentItem, { backgroundColor: settings.darkMode ? '#1a1a2e' : '#fff' }]}
              onPress={() => router.push(`/result/${item.id}`)}
            >
              <Text style={[styles.recentTitle, { color: settings.darkMode ? '#fff' : '#000' }]} numberOfLines={1}>
                {item.title}
              </Text>
              <Text style={styles.recentQuality}>{item.quality}</Text>
            </TouchableOpacity>
          ))}
        </View>
      )}
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, paddingHorizontal: 20, paddingTop: 60 },
  header: { alignItems: 'center', marginBottom: 32, marginTop: 20 },
  title: { fontSize: 32, fontWeight: '800', letterSpacing: -0.5 },
  subtitle: { fontSize: 14, marginTop: 4 },
  inputContainer: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  input: {
    flex: 1, height: 50, borderRadius: 12, paddingHorizontal: 16,
    fontSize: 16, borderWidth: 1,
  },
  goButton: {
    width: 50, height: 50, borderRadius: 12,
    backgroundColor: '#8b5cf6', alignItems: 'center', justifyContent: 'center',
  },
  goText: { color: '#fff', fontWeight: '800', fontSize: 16 },
  preview: { marginTop: 8, paddingHorizontal: 4 },
  previewLabel: { fontSize: 13 },
  section: { marginTop: 32 },
  sectionTitle: { fontSize: 18, fontWeight: '700', marginBottom: 12 },
  recentItem: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    padding: 14, borderRadius: 10, marginBottom: 8,
  },
  recentTitle: { flex: 1, fontSize: 14, fontWeight: '500' },
  recentQuality: { fontSize: 12, color: '#8b5cf6', fontWeight: '600', marginLeft: 8 },
});
