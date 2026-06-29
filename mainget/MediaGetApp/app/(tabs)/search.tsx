import { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet, FlatList, Image, ActivityIndicator,
} from 'react-native';
import { router } from 'expo-router';
import { useStore } from '../../store';
import { fetchInfo } from '../../lib/api';
import { formatDuration } from '../../lib/utils';
import type { SearchResult } from '../../types';

const platforms = ['youtube', 'tiktok'] as const;

export default function SearchScreen() {
  const [query, setQuery] = useState('');
  const [platform, setPlatform] = useState<'youtube' | 'tiktok'>('youtube');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const settings = useStore((s) => s.settings);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError('');
    try {
      const data = await fetchInfo(query.trim());
      setResults([{
        id: query.trim(),
        title: data.title,
        thumbnail: data.thumbnail,
        duration: data.duration,
        author: data.author,
        platform: platform,
      }]);
    } catch (e: any) {
      setError(e?.message || 'Search failed');
    } finally {
      setLoading(false);
    }
  };

  const handleSelect = (item: SearchResult) => {
    const url = platform === 'youtube'
      ? `https://youtube.com/watch?v=${item.id}`
      : `https://tiktok.com/@user/video/${item.id}`;
    router.push(`/result/${item.id}?url=${encodeURIComponent(url)}`);
  };

  return (
    <View style={[styles.container, { backgroundColor: settings.darkMode ? '#0a0a12' : '#f5f5f5' }]}>
      <Text style={[styles.title, { color: settings.darkMode ? '#fff' : '#000' }]}>Search</Text>

      <View style={styles.platformRow}>
        {platforms.map((p) => (
          <TouchableOpacity
            key={p}
            style={[styles.platformBtn, platform === p && styles.platformActive]}
            onPress={() => setPlatform(p)}
          >
            <Text style={[styles.platformText, platform === p && styles.platformTextActive]}>
              {p === 'youtube' ? '📺 YouTube' : '🎵 TikTok'}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <View style={styles.inputRow}>
        <TextInput
          style={[styles.input, {
            backgroundColor: settings.darkMode ? '#1a1a2e' : '#fff',
            color: settings.darkMode ? '#fff' : '#000',
            borderColor: settings.darkMode ? '#2a2a3e' : '#ddd',
          }]}
          placeholder={platform === 'youtube' ? 'Cari video YouTube...' : 'Cari TikTok..."'}
          placeholderTextColor={settings.darkMode ? '#555' : '#999'}
          value={query}
          onChangeText={setQuery}
          returnKeyType="search"
          onSubmitEditing={handleSearch}
        />
        <TouchableOpacity style={styles.searchBtn} onPress={handleSearch}>
          <Text style={styles.searchBtnText}>Cari</Text>
        </TouchableOpacity>
      </View>

      {loading && <ActivityIndicator size="large" color="#8b5cf6" style={{ marginTop: 40 }} />}

      {error ? (
        <Text style={styles.error}>{error}</Text>
      ) : (
        <FlatList
          data={results}
          keyExtractor={(item) => item.id}
          renderItem={({ item }) => (
            <TouchableOpacity
              style={[styles.card, { backgroundColor: settings.darkMode ? '#1a1a2e' : '#fff' }]}
              onPress={() => handleSelect(item)}
            >
              <Image source={{ uri: item.thumbnail }} style={styles.thumb} />
              <View style={styles.cardInfo}>
                <Text style={[styles.cardTitle, { color: settings.darkMode ? '#fff' : '#000' }]} numberOfLines={2}>
                  {item.title}
                </Text>
                <Text style={styles.cardAuthor}>{item.author}</Text>
                <Text style={styles.cardDuration}>{formatDuration(item.duration)}</Text>
              </View>
            </TouchableOpacity>
          )}
          contentContainerStyle={results.length === 0 ? { flex: 1, justifyContent: 'center', alignItems: 'center' } : { paddingTop: 16, paddingBottom: 100 }}
          ListEmptyComponent={
            !loading ? (
              <Text style={[styles.empty, { color: settings.darkMode ? '#555' : '#999' }]}>
                {query ? 'No results found' : 'Search YouTube or TikTok videos'}
              </Text>
            ) : null
          }
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, paddingHorizontal: 16, paddingTop: 60 },
  title: { fontSize: 28, fontWeight: '800', marginBottom: 16 },
  platformRow: { flexDirection: 'row', gap: 10, marginBottom: 16 },
  platformBtn: {
    paddingVertical: 8, paddingHorizontal: 16, borderRadius: 20,
    backgroundColor: '#1a1a2e',
  },
  platformActive: { backgroundColor: '#8b5cf6' },
  platformText: { color: '#888', fontWeight: '600' },
  platformTextActive: { color: '#fff' },
  inputRow: { flexDirection: 'row', gap: 10 },
  input: {
    flex: 1, height: 46, borderRadius: 10, paddingHorizontal: 14,
    fontSize: 15, borderWidth: 1,
  },
  searchBtn: {
    height: 46, paddingHorizontal: 20, borderRadius: 10,
    backgroundColor: '#8b5cf6', alignItems: 'center', justifyContent: 'center',
  },
  searchBtnText: { color: '#fff', fontWeight: '700' },
  error: { color: '#ef4444', textAlign: 'center', marginTop: 20 },
  card: {
    flexDirection: 'row', borderRadius: 12, overflow: 'hidden',
    marginBottom: 12, elevation: 2, shadowColor: '#000', shadowOpacity: 0.1,
    shadowRadius: 8, shadowOffset: { width: 0, height: 2 },
  },
  thumb: { width: 120, height: 68, backgroundColor: '#222' },
  cardInfo: { flex: 1, padding: 12, justifyContent: 'center' },
  cardTitle: { fontSize: 14, fontWeight: '600', lineHeight: 19 },
  cardAuthor: { fontSize: 12, color: '#888', marginTop: 2 },
  cardDuration: { fontSize: 11, color: '#8b5cf6', marginTop: 2, fontWeight: '600' },
  empty: { fontSize: 14, textAlign: 'center' },
});
