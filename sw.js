// Keeps the app fast and working with no signal. Bump VERSION whenever files change.
const VERSION = "v39";
const FILES = ["./", "index.html", "manifest.webmanifest", "img/daxton.jpg", "img/icon-180.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(FILES)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

// The page that just opened may not be ready to hear us yet, so try for a few seconds.
async function tellPage(id) {
  for (let i = 0; i < 20; i++) {
    const c = id && await self.clients.get(id);
    if (c) { c.postMessage("update-ready"); return; }
    await new Promise(r => setTimeout(r, 250));
  }
}

// Open instantly from the saved copy, then quietly check for a newer one in the background.
// If the page itself changed, tell the app so it can offer a one-tap refresh.
self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;
  const url = new URL(e.request.url);
  if (url.origin !== self.location.origin) return; // never touch GitHub sync calls
  if (e.request.mode === "navigate" && /\.html$/.test(url.pathname) && !/index\.html$/.test(url.pathname)) return; // other pages (Photo editor) load themselves
  const isPage = e.request.mode === "navigate";
  const key = isPage ? "index.html" : e.request;
  const cachedP = caches.open(VERSION).then(c => c.match(key, { ignoreSearch: isPage }));
  // [response for the page, spare copy for the cache]
  const freshP = fetch(isPage ? "index.html" : e.request.url, { cache: "no-cache" })
    .then(r => (r && r.ok) ? [r, r.clone()] : null).catch(() => null);
  e.respondWith(cachedP.then(cached => cached ? cached.clone() : freshP.then(f => f ? f[0] : caches.match("index.html"))));
  e.waitUntil(Promise.all([cachedP, freshP]).then(async ([cached, f]) => {
    if (!f) return;
    const copy = f[1];
    if (isPage && cached) {
      const [a, b] = await Promise.all([cached.text(), copy.clone().text()]);
      if (a !== b) await tellPage(e.resultingClientId || e.clientId);
    }
    await (await caches.open(VERSION)).put(key, copy);
  }).catch(() => {}));
});

// Lock-screen alarm sent by the GitHub alarm job (works with the app closed)
self.addEventListener("push", e => {
  let d = {}; try { d = e.data ? e.data.json() : {}; } catch (x) { d = { body: e.data && e.data.text() }; }
  e.waitUntil(self.registration.showNotification(d.title || "⏰ Alarm", {
    body: d.body || "Daxton's Life", tag: d.tag || "alarm", icon: "img/icon-192.png",
    requireInteraction: true, data: { url: d.url || "./" }
  }));
});

// Tapping any alarm clears the rest and opens the app, where Snooze / Turn off are waiting
self.addEventListener("notificationclick", e => {
  e.notification.close();
  const url = new URL((e.notification.data && e.notification.data.url) || "./", self.registration.scope).href;
  e.waitUntil(Promise.all([
    self.registration.getNotifications().then(ns => ns.forEach(n => n.close())),
    clients.matchAll({ type:"window", includeUncontrolled:true }).then(ws => ws[0] ? ws[0].focus() : clients.openWindow(url))
  ]));
});
