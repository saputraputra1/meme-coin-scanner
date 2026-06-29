import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';
import type { DownloadItem, AppSettings } from '../types';

interface AppStore {
  settings: AppSettings;
  downloads: DownloadItem[];
  isLoading: boolean;

  loadSettings: () => Promise<void>;
  updateSettings: (partial: Partial<AppSettings>) => Promise<void>;
  addDownload: (item: DownloadItem) => void;
  updateDownload: (id: string, partial: Partial<DownloadItem>) => void;
  removeDownload: (id: string) => void;
  clearDownloads: () => void;
}

const defaultSettings: AppSettings = {
  serverUrl: 'http://localhost:3000',
  darkMode: true,
  downloadQuality: 'highest',
  autoDownload: false,
};

export const useStore = create<AppStore>((set, get) => ({
  settings: defaultSettings,
  downloads: [],
  isLoading: true,

  loadSettings: async () => {
    try {
      const [settingsJson, downloadsJson] = await Promise.all([
        AsyncStorage.getItem('settings'),
        AsyncStorage.getItem('downloads'),
      ]);
      set({
        settings: settingsJson ? { ...defaultSettings, ...JSON.parse(settingsJson) } : defaultSettings,
        downloads: downloadsJson ? JSON.parse(downloadsJson) : [],
        isLoading: false,
      });
    } catch {
      set({ isLoading: false });
    }
  },

  updateSettings: async (partial) => {
    const newSettings = { ...get().settings, ...partial };
    await AsyncStorage.setItem('settings', JSON.stringify(newSettings));
    set({ settings: newSettings });
  },

  addDownload: (item) => {
    set((state) => {
      const downloads = [item, ...state.downloads].slice(0, 50);
      AsyncStorage.setItem('downloads', JSON.stringify(downloads));
      return { downloads };
    });
  },

  updateDownload: (id, partial) => {
    set((state) => {
      const downloads = state.downloads.map((d) =>
        d.id === id ? { ...d, ...partial } : d
      );
      AsyncStorage.setItem('downloads', JSON.stringify(downloads));
      return { downloads };
    });
  },

  removeDownload: (id) => {
    set((state) => {
      const downloads = state.downloads.filter((d) => d.id !== id);
      AsyncStorage.setItem('downloads', JSON.stringify(downloads));
      return { downloads };
    });
  },

  clearDownloads: async () => {
    await AsyncStorage.removeItem('downloads');
    set({ downloads: [] });
  },
}));
