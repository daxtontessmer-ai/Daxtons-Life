// Keeps the app fast and working with no signal. Bump VERSION whenever files change.
const VERSION = "v46";
const FILES = ["./", "index.html", "manifest.webmanifest", "img/daxton.jpg", "img/icon-180.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(FILES)).then(() => self.skipWaiting()));
});

// Reload open copies so an installed home-screen app matches the site as soon as this worker takes over.
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

// Online: the home page comes from the network. Offline: fall back to the saved copy.
// Other HTML pages (the photo editor) are left to the browser.
self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;
  const url = new URL(e.request.url);
  if (url.origin !== self.location.origin) return; // never touch GitHub sync calls
  if (e.request.mode === "navigate" && /\.html$/.test(url.pathname) && !/index\.html$/.test(url.pathname)) return;
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
  const key = e.request;
  const cachedP = caches.open(VERSION).then(c => c.match(key));
  const freshP = fetch(e.request.url, { cache: "no-cache" })
    .then(r => (r && r.ok) ? [r, r.clone()] : null).catch(() => null);
  e.respondWith(cachedP.then(cached => cached ? cached.clone() : freshP.then(f => f ? f[0] : undefined)));
  e.waitUntil(Promise.all([cachedP, freshP]).then(async ([, f]) => {
    if (!f) return;
    await (await caches.open(VERSION)).put(key, f[1]);
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
