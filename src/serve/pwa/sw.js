const CACHE_SHELL = 'mpmb-pwa-shell-v2';
const CACHE_API_PREFIX = 'mpmb-pwa-api-v2-';
const MAX_CACHED_PAGE_ENTRIES = 30;
const SHELL_ASSETS = ['/', '/style.css', '/app.js', '/manifest.webmanifest', '/icon.svg'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_SHELL).then((cache) => cache.addAll(SHELL_ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== CACHE_SHELL && !k.startsWith(CACHE_API_PREFIX))
          .map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'CLEAR_API_CACHE') {
    event.waitUntil(
      caches.keys().then((keys) =>
        Promise.all(keys.filter((k) => k.startsWith(CACHE_API_PREFIX)).map((k) => caches.delete(k)))
      )
    );
  }
});

async function apiCacheNameFor(req) {
  const auth = req.headers.get('authorization') || '';
  if (!auth) return `${CACHE_API_PREFIX}anon`;
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(auth));
  const hex = Array.from(new Uint8Array(digest)).slice(0, 8).map((b) => b.toString(16).padStart(2, '0')).join('');
  return `${CACHE_API_PREFIX}${hex}`;
}

async function putAndPruneApiCache(cacheName, req, res) {
  const cache = await caches.open(cacheName);
  await cache.put(req, res);
  const reqUrl = new URL(req.url);
  if (!reqUrl.pathname.startsWith('/api/session/page/')) return;
  const keys = await cache.keys();
  const pageKeys = keys.filter((k) => new URL(k.url).pathname.startsWith('/api/session/page/'));
  const excess = pageKeys.length - MAX_CACHED_PAGE_ENTRIES;
  if (excess > 0) {
    await Promise.all(pageKeys.slice(0, excess).map((k) => cache.delete(k)));
  }
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);

  // Cache-first with network update for shell assets.
  if (SHELL_ASSETS.includes(url.pathname)) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res.ok) {
            const copy = res.clone();
            event.waitUntil(
              caches.open(CACHE_SHELL).then((c) => c.put(req, copy)).catch(() => {})
            );
          }
          return res;
        })
        .catch(() => caches.match(req))
    );
    return;
  }

  // Network-first with credential-partitioned offline cache fallback.
  // Page image/widget URLs must include sheet & rev query parameters so switching
  // sheets never serves another sheet's cached page snapshot.
  const isStateOrSheets = url.pathname === '/api/session/state' || url.pathname === '/api/sheets';
  const isSheetKeyedPage =
    url.pathname.startsWith('/api/session/page/') &&
    url.searchParams.has('sheet') &&
    url.searchParams.has('rev');

  if (isStateOrSheets || isSheetKeyedPage) {
    event.respondWith(
      (async () => {
        const cacheName = await apiCacheNameFor(req);
        let res;
        try {
          res = await fetch(req);
        } catch (_) {
          const cache = await caches.open(cacheName);
          const cached = await cache.match(req);
          if (cached) return cached;
          throw new Error('Offline and no cached response available');
        }
        if (res.ok) {
          const copy = res.clone();
          event.waitUntil(putAndPruneApiCache(cacheName, req, copy).catch(() => {}));
        }
        return res;
      })()
    );
  }
});
