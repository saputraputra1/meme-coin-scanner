import axios from 'axios';

const getBaseUrl = () => {
  // default server URL — can be changed in settings
  return 'http://localhost:3000';
};

const api = axios.create({
  timeout: 30000,
  headers: { 'Accept': 'application/json' },
});

api.interceptors.request.use((config) => {
  config.baseURL = getBaseUrl();
  return config;
});

export interface FetchInfoResponse {
  title: string;
  thumbnail: string;
  duration: number;
  author: string;
  formats: Array<{
    itag: number;
    url: string;
    mimeType: string;
    quality: string;
    qualityLabel?: string;
    hasAudio: boolean;
    hasVideo: boolean;
    contentLength?: string;
    fps?: number;
  }>;
  platform: string;
}

export const fetchInfo = async (url: string): Promise<FetchInfoResponse> => {
  const { data } = await api.post('/api/fetch-info', { url });
  return data;
};

export const getDownloadUrl = async (url: string, formatId: string): Promise<string> => {
  const { data } = await api.post('/api/yt-download', { url, formatId });
  return data.downloadUrl || data.url;
};

export const searchMedia = async (query: string, platform: string): Promise<any[]> => {
  const { data } = await api.get('/api/search', { params: { q: query, platform } });
  return data.results || data;
};

export const downloadFile = async (downloadUrl: string, filename: string): Promise<string> => {
  const { data } = await api.get(downloadUrl, {
    responseType: 'blob',
    onDownloadProgress: undefined,
  });
  return data;
};

export const checkServer = async (serverUrl: string): Promise<boolean> => {
  try {
    const { status } = await axios.get(`${serverUrl}/api/search`, { timeout: 5000 });
    return status === 200;
  } catch {
    return false;
  }
};

export default api;
