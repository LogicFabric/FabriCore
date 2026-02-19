self.addEventListener('install', function (event) {
    console.log('Service Worker: Installing...');
    self.skipWaiting();
});

self.addEventListener('activate', function (event) {
    console.log('Service Worker: Activated');
});

self.addEventListener('fetch', function (event) {
    // Basic fetch listener required for PWA installability
    // Can be used for caching later
});

self.addEventListener('push', function (event) {
    if (event.data) {
        let payload;
        try {
            payload = event.data.json();
        } catch (e) {
            payload = { title: "FabriCore", body: event.data.text() };
        }

        const options = {
            body: payload.body,
            icon: '/static/pwa/icon-192.png',
            badge: '/static/pwa/icon-192.png',
            tag: 'fabricore-alert',
            renotify: true,
            data: { url: payload.url || '/' },
            vibrate: [100, 50, 100],
            actions: [
                { action: 'open', title: 'Open FabriCore' }
            ]
        };
        event.waitUntil(
            self.registration.showNotification(payload.title, options)
        );
    }
});

self.addEventListener('notificationclick', function (event) {
    event.notification.close();
    event.waitUntil(
        clients.openWindow(event.notification.data.url)
    );
});
