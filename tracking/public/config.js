// Auto-detect: local → localhost, produksi → Railway
const SERVER_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? 'http://localhost:8080'
    : 'https://trackingg.up.railway.app';
