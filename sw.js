// Keeps the app working with no signal. Bump VERSION whenever files change.
const VERSION = "v10-instagram-downloader";
const FILES = ["./", "index.html", "video.html", "manifest.webmanifest", "img/daxton.jpg", "img/icon-180.png", "img/icon-192.png", "img/icon-512.png"];

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
  // dl-ffmpeg* is the converter engine, saved by the video page. Keep it across app updates.
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== VERSION && !k.startsWith("dl-ffmpeg")).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
  setTimeout(() => { refreshClients(); }, 50);
});

// Online: the page comes from the network. Offline: the saved copy.
self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;
  const url = new URL(e.request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.endsWith("/sw.js")) return; // let the browser fetch this file itself so an update is never a stale copy
  // video.html must not be saved over the home page. Cache it on its own.
  if (e.request.mode === "navigate" && /\/video\.html$/.test(url.pathname)) {
    e.respondWith((async () => {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 8000);
      try {
        const fresh = await fetch("video.html", { cache: "no-store", credentials: "same-origin", signal: ctrl.signal });
        if (fresh && fresh.ok) {
          const copy = fresh.clone();
          caches.open(VERSION).then(c => c.put("video.html", copy)).catch(() => {});
          return fresh;
        }
      } catch (err) {}
      finally { clearTimeout(timer); }
      return (await caches.match("video.html")) || Response.error();
    })());
    return;
  }
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
