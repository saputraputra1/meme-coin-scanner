import { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet, Switch, Alert,
} from 'react-native';
import { useStore } from '../../store';
import { checkServer } from '../../lib/api';

export default function SettingsScreen() {
  const settings = useStore((s) => s.settings);
  const updateSettings = useStore((s) => s.updateSettings);
  const [urlInput, setUrlInput] = useState(settings.serverUrl);
  const [testing, setTesting] = useState(false);

  const handleTestServer = async () => {
    setTesting(true);
    const ok = await checkServer(urlInput);
    setTesting(false);
    if (ok) {
      await updateSettings({ serverUrl: urlInput });
      Alert.alert('Connected', 'Server is reachable ✓');
    } else {
      Alert.alert('Failed', 'Cannot reach server. Check the URL.');
    }
  };

  const handleSaveServer = async () => {
    await updateSettings({ serverUrl: urlInput });
    Alert.alert('Saved', 'Server URL updated');
  };

  return (
    <View style={[styles.container, { backgroundColor: settings.darkMode ? '#0a0a12' : '#f5f5f5' }]}>
      <Text style={[styles.title, { color: settings.darkMode ? '#fff' : '#000' }]}>Settings</Text>

      <View style={styles.section}>
        <Text style={[styles.sectionTitle, { color: settings.darkMode ? '#ccc' : '#333' }]}>Server</Text>
        <TextInput
          style={[styles.input, {
            backgroundColor: settings.darkMode ? '#1a1a2e' : '#fff',
            color: settings.darkMode ? '#fff' : '#000',
            borderColor: settings.darkMode ? '#2a2a3e' : '#ddd',
          }]}
          value={urlInput}
          onChangeText={setUrlInput}
          placeholder="http://localhost:3000"
          placeholderTextColor="#555"
          autoCapitalize="none"
          autoCorrect={false}
        />
        <View style={styles.btnRow}>
          <TouchableOpacity style={styles.btnOutline} onPress={handleTestServer} disabled={testing}>
            <Text style={styles.btnOutlineText}>{testing ? 'Testing...' : 'Test'}</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.btnPrimary} onPress={handleSaveServer}>
            <Text style={styles.btnPrimaryText}>Save</Text>
          </TouchableOpacity>
        </View>
      </View>

      <View style={styles.section}>
        <Text style={[styles.sectionTitle, { color: settings.darkMode ? '#ccc' : '#333' }]}>Preferences</Text>

        <View style={styles.settingRow}>
          <Text style={[styles.settingLabel, { color: settings.darkMode ? '#fff' : '#000' }]}>Dark Mode</Text>
          <Switch
            value={settings.darkMode}
            onValueChange={(v) => updateSettings({ darkMode: v })}
            trackColor={{ false: '#333', true: '#6d28d9' }}
            thumbColor={settings.darkMode ? '#8b5cf6' : '#ccc'}
          />
        </View>

        <View style={styles.settingRow}>
          <Text style={[styles.settingLabel, { color: settings.darkMode ? '#fff' : '#000' }]}>Auto Download</Text>
          <Switch
            value={settings.autoDownload}
            onValueChange={(v) => updateSettings({ autoDownload: v })}
            trackColor={{ false: '#333', true: '#6d28d9' }}
            thumbColor={settings.autoDownload ? '#8b5cf6' : '#ccc'}
          />
        </View>
      </View>

      <View style={styles.footer}>
        <Text style={styles.footerText}>MediaGet v1.0.0</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, paddingHorizontal: 16, paddingTop: 60 },
  title: { fontSize: 28, fontWeight: '800', marginBottom: 24 },
  section: { marginBottom: 28 },
  sectionTitle: { fontSize: 13, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 10 },
  input: {
    height: 46, borderRadius: 10, paddingHorizontal: 14,
    fontSize: 15, borderWidth: 1,
  },
  btnRow: { flexDirection: 'row', gap: 10, marginTop: 10 },
  btnOutline: {
    flex: 1, height: 42, borderRadius: 10, borderWidth: 1.5,
    borderColor: '#8b5cf6', alignItems: 'center', justifyContent: 'center',
  },
  btnOutlineText: { color: '#8b5cf6', fontWeight: '700', fontSize: 14 },
  btnPrimary: {
    flex: 1, height: 42, borderRadius: 10,
    backgroundColor: '#8b5cf6', alignItems: 'center', justifyContent: 'center',
  },
  btnPrimaryText: { color: '#fff', fontWeight: '700', fontSize: 14 },
  settingRow: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: '#1e1e30',
  },
  settingLabel: { fontSize: 16, fontWeight: '500' },
  footer: { marginTop: 'auto', alignItems: 'center', paddingBottom: 40 },
  footerText: { color: '#555', fontSize: 12 },
});
