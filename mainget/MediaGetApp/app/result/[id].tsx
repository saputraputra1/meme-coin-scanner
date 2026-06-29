import { useState, useEffect, useCallback } from 'react';
import {
  View, Text, Image, TouchableOpacity, StyleSheet, ScrollView,
  ActivityIndicator, Alert, Platform,
} from 'react-native';
import { useLocalSearchParams, router } from 'expo-router';
import { File, Directory, Paths } from 'expo-file-system';
import * as MediaLibrary from 'expo-media-library';
import * as Sharing from 'expo-sharing';
import { useStore } from '../../store';
import { fetchInfo, getDownloadUrl } from '../../lib/api';
import { formatDuration, formatBytes, generateId } from '../../lib/utils';
import type { Format } from '../../types';

export default function ResultScreen() {
  const { id, url } = useLocalSearchParams<{ id: string; url: string }>();
  const settings = useStore((s) => s.settings);
  const addDownload = useStore((s) => s.addDownload);
  const updateDownload = useStore((s) => s.updateDownload);

  const [media, setMedia] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedFormat, setSelectedFormat] = useState<Format | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    if (url) loadMedia(url);
  }, [url]);

  const loadMedia = async (videoUrl: string) => {
    setLoading(true);
    setError('');
    try {
      const data = await fetchInfo(videoUrl);
      setMedia(data);
      if (data.formats?.length > 0) {
        const best = data.formats.find(
          (f: Format) => f.hasVideo && f.hasAudio && f.qualityLabel?.includes('1080')
        ) || data.formats.find(
          (f: Format) => f.hasVideo && f.hasAudio
        ) || data.formats[0];
        setSelectedFormat(best);
      }
    } catch (e: any) {
      setError(e?.message || 'Failed to load media info');
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = useCallback(async () => {
    if (!selectedFormat || !url || !media) return;

    const downloadId = generateId();
    const fileExt = selectedFormat.mimeType?.includes('audio') ? 'mp3' : 'mp4';

    addDownload({
      id: downloadId, url, title: media.title, quality: selectedFormat.qualityLabel ||
      selectedFormat.quality, platform: media.platform || 'youtube',
      progress: 0, status: 'downloading', thumbnail: media.thumbnail, createdAt: Date.now(),
    });

    setDownloading(true);
    setProgress(0);

    try {
      const downloadUrl = await getDownloadUrl(url, `pytube_${selectedFormat.itag}`);

      const destDir = new Directory(Paths.document, 'downloads');
      destDir.create({ idempotent: true });
      const destFile = new File(destDir, `${downloadId}.${fileExt}`);

      const downloadTask = File.createDownloadTask(downloadUrl, destFile, {
        onProgress: ({ bytesWritten, totalBytes }) => {
          const pct = totalBytes > 0 ? Math.round((bytesWritten / totalBytes) * 100) : 0;
          setProgress(pct);
          updateDownload(downloadId, { progress: pct });
        },
      });

      const result = await downloadTask.downloadAsync();
      if (!result?.uri) throw new Error('Download failed');

      updateDownload(downloadId, { status: 'completed', progress: 100, fileUri: result.uri });

      const outUri = result.uri;
      Alert.alert('Download Complete', media.title, [
        { text: 'Share', onPress: () => Sharing.shareAsync(outUri) },
        {
          text: 'Save to Gallery',
          onPress: async () => {
            const { status } = await MediaLibrary.requestPermissionsAsync();
            if (status === 'granted') {
              await MediaLibrary.saveToLibraryAsync(outUri);
              Alert.alert('Saved', 'Video saved to gallery ✓');
            }
          },
        },
        { text: 'OK' },
      ]);
    } catch (e: any) {
      updateDownload(downloadId, { status: 'failed' });
      Alert.alert('Download Failed', e?.message || 'Unknown error');
    } finally {
      setDownloading(false);
      setProgress(0);
    }
  }, [selectedFormat, url, media]);

  const formatsByType = (media?.formats || []).reduce((acc: any, f: Format) => {
    if (f.hasVideo && f.hasAudio) acc.combined.push(f);
    else if (f.hasVideo) acc.video.push(f);
    else if (f.hasAudio) acc.audio.push(f);
    return acc;
  }, { combined: [] as Format[], video: [] as Format[], audio: [] as Format[] });

  if (loading) {
    return (
      <View style={[styles.container, styles.center, { backgroundColor: settings.darkMode ? '#0a0a12' : '#f5f5f5' }]}>
        <ActivityIndicator size="large" color="#8b5cf6" />
        <Text style={[styles.loadingText, { color: settings.darkMode ? '#aaa' : '#666' }]}>Fetching media info...</Text>
      </View>
    );
  }

  if (error) {
    return (
      <View style={[styles.container, styles.center, { backgroundColor: settings.darkMode ? '#0a0a12' : '#f5f5f5' }]}>
        <Text style={styles.errorIcon}>⚠️</Text>
        <Text style={styles.errorText}>{error}</Text>
        <TouchableOpacity style={styles.retryBtn} onPress={() => url && loadMedia(url)}>
          <Text style={styles.retryText}>Retry</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <ScrollView style={[styles.container, { backgroundColor: settings.darkMode ? '#0a0a12' : '#f5f5f5' }]}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()}>
          <Text style={[styles.backBtn, { color: settings.darkMode ? '#fff' : '#000' }]}>← Back</Text>
        </TouchableOpacity>
      </View>

      <Image source={{ uri: media?.thumbnail }} style={styles.thumbnail} />

      <View style={styles.info}>
        <Text style={[styles.title, { color: settings.darkMode ? '#fff' : '#000' }]}>
          {media?.title}
        </Text>
        <Text style={styles.author}>{media?.author}</Text>
        <Text style={styles.duration}>{formatDuration(media?.duration || 0)}</Text>
      </View>

      <View style={styles.section}>
        <Text style={[styles.sectionTitle, { color: settings.darkMode ? '#ccc' : '#333' }]}>
          Format & Quality
        </Text>

        {formatsByType.combined.length > 0 && (
          <>
            <Text style={styles.formatLabel}>🎬 Video + Audio</Text>
            {formatsByType.combined.map((f: Format) => (
              <TouchableOpacity
                key={f.itag}
                style={[
                  styles.formatItem,
                  selectedFormat?.itag === f.itag && styles.formatSelected,
                  { backgroundColor: settings.darkMode ? '#1a1a2e' : '#fff' },
                ]}
                onPress={() => setSelectedFormat(f)}
              >
                <Text style={[
                  styles.formatName,
                  { color: settings.darkMode ? '#fff' : '#000' },
                  selectedFormat?.itag === f.itag && { color: '#8b5cf6' },
                ]}>
                  {f.qualityLabel || f.quality}
                </Text>
                <Text style={styles.formatMeta}>
                  {f.fps ? `${f.fps}fps` : ''}
                  {f.contentLength ? ` • ${formatBytes(parseInt(f.contentLength))}` : ''}
                </Text>
              </TouchableOpacity>
            ))}
          </>
        )}

        {formatsByType.video.length > 0 && (
          <>
            <Text style={styles.formatLabel}>🎥 Video Only</Text>
            {formatsByType.video.slice(0, 6).map((f: Format) => (
              <TouchableOpacity
                key={f.itag}
                style={[
                  styles.formatItem,
                  selectedFormat?.itag === f.itag && styles.formatSelected,
                  { backgroundColor: settings.darkMode ? '#1a1a2e' : '#fff' },
                ]}
                onPress={() => setSelectedFormat(f)}
              >
                <Text style={[
                  styles.formatName,
                  { color: settings.darkMode ? '#fff' : '#000' },
                  selectedFormat?.itag === f.itag && { color: '#8b5cf6' },
                ]}>
                  {f.qualityLabel || f.quality}
                </Text>
                <Text style={styles.formatMeta}>
                  {f.fps ? `${f.fps}fps` : ''}
                  {f.contentLength ? ` • ${formatBytes(parseInt(f.contentLength))}` : ''}
                </Text>
              </TouchableOpacity>
            ))}
          </>
        )}

        {formatsByType.audio.length > 0 && (
          <>
            <Text style={styles.formatLabel}>🎵 Audio Only</Text>
            {formatsByType.audio.slice(0, 3).map((f: Format) => (
              <TouchableOpacity
                key={f.itag}
                style={[
                  styles.formatItem,
                  selectedFormat?.itag === f.itag && styles.formatSelected,
                  { backgroundColor: settings.darkMode ? '#1a1a2e' : '#fff' },
                ]}
                onPress={() => setSelectedFormat(f)}
              >
                <Text style={[
                  styles.formatName,
                  { color: settings.darkMode ? '#fff' : '#000' },
                  selectedFormat?.itag === f.itag && { color: '#8b5cf6' },
                ]}>
                  {f.qualityLabel || f.quality || `${f.audioBitrate}kbps`}
                </Text>
                <Text style={styles.formatMeta}>
                  {f.audioBitrate ? `${f.audioBitrate}kbps` : ''}
                  {f.contentLength ? ` • ${formatBytes(parseInt(f.contentLength))}` : ''}
                </Text>
              </TouchableOpacity>
            ))}
          </>
        )}
      </View>

      {downloading && (
        <View style={styles.progressBar}>
          <View style={[styles.progressFill, { width: `${progress}%` }]} />
          <Text style={styles.progressText}>Downloading... {progress}%</Text>
        </View>
      )}

      <View style={styles.actionRow}>
        {media?.formats?.some((f: Format) => f.hasVideo) && (
          <TouchableOpacity
            style={[styles.actionBtn, styles.previewBtn]}
            onPress={() => router.push(`/player/${id}?url=${encodeURIComponent(url || '')}`)}
          >
            <Text style={styles.actionBtnText}>▶ Preview</Text>
          </TouchableOpacity>
        )}

        <TouchableOpacity
          style={[
            styles.actionBtn, styles.downloadBtn,
            (!selectedFormat || downloading) && styles.disabledBtn,
          ]}
          onPress={handleDownload}
          disabled={!selectedFormat || downloading}
        >
          <Text style={styles.actionBtnText}>
            {downloading ? `⬇ ${progress}%` : '⬇ Download'}
          </Text>
        </TouchableOpacity>
      </View>

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

const container = { flex: 1 };
const styles = StyleSheet.create({
  container, center: { justifyContent: 'center', alignItems: 'center' },
  loadingText: { marginTop: 12, fontSize: 14 },
  errorIcon: { fontSize: 40, marginBottom: 12 },
  errorText: { color: '#ef4444', fontSize: 14, textAlign: 'center', marginBottom: 16, paddingHorizontal: 20 },
  retryBtn: {
    paddingVertical: 10, paddingHorizontal: 28, borderRadius: 10,
    backgroundColor: '#8b5cf6',
  },
  retryText: { color: '#fff', fontWeight: '700' },
  header: { paddingHorizontal: 16, paddingTop: 56, paddingBottom: 8 },
  backBtn: { fontSize: 16, fontWeight: '600' },
  thumbnail: { width: '100%', aspectRatio: 16 / 9, backgroundColor: '#111' },
  info: { padding: 16 },
  title: { fontSize: 18, fontWeight: '700', lineHeight: 24 },
  author: { fontSize: 13, color: '#888', marginTop: 4 },
  duration: { fontSize: 13, color: '#8b5cf6', marginTop: 2, fontWeight: '600' },
  section: { paddingHorizontal: 16, marginBottom: 16 },
  sectionTitle: { fontSize: 13, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 12 },
  formatLabel: { fontSize: 14, fontWeight: '600', color: '#aaa', marginTop: 8, marginBottom: 6 },
  formatItem: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    padding: 14, borderRadius: 10, marginBottom: 6,
  },
  formatSelected: { borderWidth: 1.5, borderColor: '#8b5cf6' },
  formatName: { fontSize: 15, fontWeight: '600' },
  formatMeta: { fontSize: 12, color: '#888' },
  progressBar: {
    marginHorizontal: 16, height: 36, borderRadius: 10,
    backgroundColor: '#1a1a2e', overflow: 'hidden', justifyContent: 'center',
    marginBottom: 12,
  },
  progressFill: {
    position: 'absolute', left: 0, top: 0, bottom: 0,
    backgroundColor: '#8b5cf6', borderRadius: 10,
  },
  progressText: { textAlign: 'center', color: '#fff', fontWeight: '700', fontSize: 12 },
  actionRow: { flexDirection: 'row', gap: 12, paddingHorizontal: 16, marginBottom: 20 },
  actionBtn: {
    flex: 1, height: 50, borderRadius: 12,
    alignItems: 'center', justifyContent: 'center',
  },
  previewBtn: { backgroundColor: '#1e1e30' },
  downloadBtn: { backgroundColor: '#8b5cf6' },
  disabledBtn: { opacity: 0.4 },
  actionBtnText: { color: '#fff', fontWeight: '700', fontSize: 16 },
});
