// Sorting Hat offline cache. Bump VERSION when index.html changes.
const VERSION = "sh-v8";
const CORE = ["./", "index.html", "manifest.json", "icon.png", "hat.png",
  "audio/gryffindor-1.m4a", "audio/gryffindor-2.m4a", "audio/hufflepuff-1.m4a", "audio/hufflepuff-2.m4a",
  "audio/slytherin-1.m4a", "audio/slytherin-2.m4a", "audio/birthday-gryffindor.m4a", "audio/cheer.m4a"];
self.addEventListener("install", e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(CORE)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== VERSION).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  const isFont = /fonts\.(googleapis|gstatic)\.com$/.test(url.hostname);
  if (url.origin !== location.origin && !isFont) return;
  // Network first for the page (so updates arrive), cache fallback offline; cache first for fonts/assets.
  if (req.mode === "navigate") {
    e.respondWith(fetch(req).then(r => { const c = r.clone(); caches.open(VERSION).then(x => x.put("index.html", c)); return r; })
      .catch(() => caches.match("index.html")));
    return;
  }
  e.respondWith(caches.match(req).then(hit => hit || fetch(req).then(r => {
    const c = r.clone(); caches.open(VERSION).then(x => x.put(req, c)); return r;
  })));
});
