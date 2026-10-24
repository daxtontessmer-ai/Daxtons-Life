// Keeps the app working with no signal. Bump VERSION whenever files change.
const VERSION = "v7";
const FILES = ["./", "index.html", "manifest.webmanifest", "img/daxton.jpg", "img/icon-180.png", "img/icon-192.png", "img/icon-512.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(FILES)).then(() => self.skipWaiting()));
});

async function refreshClients() {
  const list = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
  await Promise.all(list.map(async c => {
    if (c.navigate) { try { await c.navigate(c.url); return; } catch (err) {} }
    c.postMessage("reload");
  }));
}

self.addEventListener("activate", e => {
  // Finish activating before reloading. Navigating inside this waitUntil deadlocks the page load.
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
  setTimeout(() => { refreshClients(); }, 50);
});

// Online: the page comes from the network. Offline: the saved copy.
self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;
  const url = new URL(e.request.url);
  if (url.origin !== self.location.origin) return;
  const isPage = e.request.mode === "navigate";
  if (isPage) {
    e.respondWith((async () => {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 8000);
      try {
        const fresh = await fetch(e.request.url, { cache: "no-store", credentials: "same-origin", signal: ctrl.signal });
        if (fresh && fresh.ok) {
          const copy = fresh.clone();
          caches.open(VERSION).then(c => c.put("index.html", copy)).catch(() => {});
          return fresh;
        }
      } catch (err) {}
      finally { clearTimeout(timer); }
      return (await caches.match("index.html")) || (await caches.match(e.request, { ignoreSearch: true })) || Response.error();
    })());
    return;
  }
  e.respondWith((async () => {
    try {
      const fresh = await fetch(e.request.url, { cache: "no-cache" });
      if (fresh && fresh.ok) {
        const copy = fresh.clone();
        caches.open(VERSION).then(c => c.put(e.request, copy)).catch(() => {});
        return fresh;
      }
    } catch (err) {}
    return (await caches.match(e.request)) || (await caches.match("index.html")) || Response.error();
  })());
});
