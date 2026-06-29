import { useState, useEffect, useRef } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import { useLocalSearchParams, router } from 'expo-router';
import { VideoView, useVideoPlayer } from 'expo-video';
import { useStore } from '../../store';
import { fetchInfo, getDownloadUrl } from '../../lib/api';

export default function PlayerScreen() {
  const { id, url } = useLocalSearchParams<{ id: string; url: string }>();
  const settings = useStore((s) => s.settings);
  const [streamUrl, setStreamUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const player = useVideoPlayer(streamUrl || '', (player) => {
    player.loop = false;
    player.showNowPlayingNotification = false;
  });

  useEffect(() => {
    loadStream();
  }, []);

  const loadStream = async () => {
    if (!url) return;
    setLoading(true);
    try {
      const info = await fetchInfo(url);
      const format = info.formats?.find(
        (f: any) => f.hasVideo && f.hasAudio
      ) || info.formats?.[0];

      if (!format) throw new Error('No suitable format found');

      const downloadUrl = await getDownloadUrl(url, `pytube_${format.itag}`);
      setStreamUrl(downloadUrl);
      player.replace(downloadUrl);
      player.play();
    } catch (e: any) {
      setError(e?.message || 'Failed to load video');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <View style={[styles.container, styles.center, { backgroundColor: '#000' }]}>
        <ActivityIndicator size="large" color="#8b5cf6" />
        <Text style={styles.loadingText}>Loading video...</Text>
      </View>
    );
  }

  if (error) {
    return (
      <View style={[styles.container, styles.center, { backgroundColor: '#000' }]}>
        <Text style={styles.errorIcon}>⚠️</Text>
        <Text style={styles.errorText}>{error}</Text>
        <TouchableOpacity style={styles.retryBtn} onPress={loadStream}>
          <Text style={styles.retryText}>Retry</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={[styles.container, { backgroundColor: '#000' }]}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()}>
          <Text style={styles.backBtn}>✕ Close</Text>
        </TouchableOpacity>
      </View>

      {streamUrl && (
        <VideoView
          player={player}
          style={styles.video}
          contentFit="contain"
          nativeControls
        />
      )}

      <View style={styles.controls}>
        <TouchableOpacity
          style={styles.controlBtn}
          onPress={() => player.play()}
        >
          <Text style={styles.controlText}>▶ Play</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.controlBtn}
          onPress={() => player.pause()}
        >
          <Text style={styles.controlText}>⏸ Pause</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  center: { justifyContent: 'center', alignItems: 'center' },
  loadingText: { color: '#aaa', marginTop: 12, fontSize: 14 },
  errorIcon: { fontSize: 40, marginBottom: 12 },
  errorText: { color: '#ef4444', fontSize: 14, textAlign: 'center', marginBottom: 16 },
  retryBtn: {
    paddingVertical: 10, paddingHorizontal: 28, borderRadius: 10,
    backgroundColor: '#8b5cf6',
  },
  retryText: { color: '#fff', fontWeight: '700' },
  header: { paddingHorizontal: 16, paddingTop: 56, paddingBottom: 8 },
  backBtn: { color: '#fff', fontSize: 16, fontWeight: '600' },
  video: { flex: 1 },
  controls: {
    flexDirection: 'row', justifyContent: 'center', gap: 20,
    paddingVertical: 20, paddingBottom: 40,
  },
  controlBtn: {
    paddingVertical: 10, paddingHorizontal: 24, borderRadius: 10,
    backgroundColor: '#1a1a2e',
  },
  controlText: { color: '#fff', fontWeight: '600' },
});
