export interface Format {
  itag: number;
  url: string;
  mimeType: string;
  quality: string;
  qualityLabel?: string;
  bitrate?: number;
  audioBitrate?: number;
  contentLength?: string;
  hasAudio: boolean;
  hasVideo: boolean;
  fps?: number;
}

export interface MediaInfo {
  title: string;
  thumbnail: string;
  duration: number;
  author: string;
  formats: Format[];
  adaptiveFormats?: Format[];
  platform: 'youtube' | 'tiktok' | 'instagram' | 'facebook';
}

export interface SearchResult {
  id: string;
  title: string;
  thumbnail: string;
  duration: number;
  author: string;
  platform: 'youtube' | 'tiktok';
}

export interface DownloadItem {
  id: string;
  url: string;
  title: string;
  quality: string;
  platform: string;
  progress: number;
  status: 'downloading' | 'completed' | 'failed';
  fileUri?: string;
  thumbnail?: string;
  createdAt: number;
}

export interface AppSettings {
  serverUrl: string;
  darkMode: boolean;
  downloadQuality: string;
  autoDownload: boolean;
}
