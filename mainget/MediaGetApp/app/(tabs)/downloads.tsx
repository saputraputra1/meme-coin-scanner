import { View, Text, FlatList, TouchableOpacity, StyleSheet, Image } from 'react-native';
import { router } from 'expo-router';
import { useStore } from '../../store';

export default function DownloadsScreen() {
  const settings = useStore((s) => s.settings);
  const downloads = useStore((s) => s.downloads);
  const clearDownloads = useStore((s) => s.clearDownloads);

  const renderItem = ({ item }: any) => (
    <View style={[styles.card, { backgroundColor: settings.darkMode ? '#1a1a2e' : '#fff' }]}>
      {item.thumbnail && (
        <Image source={{ uri: item.thumbnail }} style={styles.thumb} />
      )}
      <View style={styles.info}>
        <Text style={[styles.title, { color: settings.darkMode ? '#fff' : '#000' }]} numberOfLines={2}>
          {item.title}
        </Text>
        <Text style={styles.meta}>
          {item.quality} • {item.platform}
        </Text>
        <View style={styles.statusRow}>
          <View style={[
            styles.statusBadge,
            item.status === 'completed' && styles.statusDone,
            item.status === 'downloading' && styles.statusProgress,
            item.status === 'failed' && styles.statusFailed,
          ]}>
            <Text style={styles.statusText}>
              {item.status === 'completed' ? '✓ Done' :
               item.status === 'downloading' ? `⬇ ${item.progress}%` :
               '✗ Failed'}
            </Text>
          </View>
        </View>
      </View>
    </View>
  );

  return (
    <View style={[styles.container, { backgroundColor: settings.darkMode ? '#0a0a12' : '#f5f5f5' }]}>
      <View style={styles.header}>
        <Text style={[styles.title, { color: settings.darkMode ? '#fff' : '#000' }]}>Downloads</Text>
        {downloads.length > 0 && (
          <TouchableOpacity onPress={clearDownloads}>
            <Text style={styles.clearBtn}>Clear All</Text>
          </TouchableOpacity>
        )}
      </View>

      <FlatList
        data={downloads}
        keyExtractor={(item) => item.id}
        renderItem={renderItem}
        contentContainerStyle={downloads.length === 0 ? { flex: 1, justifyContent: 'center', alignItems: 'center' } : { paddingBottom: 100 }}
        ListEmptyComponent={
          <Text style={[styles.empty, { color: settings.darkMode ? '#555' : '#999' }]}>
            No downloads yet
          </Text>
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, paddingHorizontal: 16, paddingTop: 60 },
  header: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    marginBottom: 20,
  },
  title: { fontSize: 28, fontWeight: '800' },
  clearBtn: { color: '#ef4444', fontWeight: '600', fontSize: 14 },
  card: {
    flexDirection: 'row', borderRadius: 12, overflow: 'hidden',
    marginBottom: 10, elevation: 2, shadowColor: '#000', shadowOpacity: 0.1,
    shadowRadius: 6, shadowOffset: { width: 0, height: 2 },
  },
  thumb: { width: 100, height: 56, backgroundColor: '#222' },
  info: { flex: 1, padding: 12, justifyContent: 'center' },
  meta: { fontSize: 12, color: '#888', marginTop: 2 },
  statusRow: { flexDirection: 'row', marginTop: 6 },
  statusBadge: {
    paddingVertical: 2, paddingHorizontal: 8, borderRadius: 6,
    backgroundColor: '#333',
  },
  statusDone: { backgroundColor: '#065f46' },
  statusProgress: { backgroundColor: '#1e40af' },
  statusFailed: { backgroundColor: '#7f1d1d' },
  statusText: { color: '#fff', fontSize: 11, fontWeight: '600' },
  empty: { fontSize: 14, textAlign: 'center' },
});
