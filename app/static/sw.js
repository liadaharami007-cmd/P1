// P1 AI service worker — מעטפת האפליקציה זמינה גם בלי רשת. נתונים (API) לעולם לא נשמרים במטמון:
// בלי רשת מוצג מסך "אין חיבור" ולא נתונים ישנים שמתחזים לעדכניים.
const VERSION = "p1-shell-v1";
const SHELL = ["/", "/static/offline.html", "/static/css/app.css", "/static/favicon.svg", "/static/pwa/icon-192.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/demo-store")) return; // רשת בלבד
  if (e.request.mode === "navigate") {
    e.respondWith(fetch(e.request).catch(() => caches.match("/static/offline.html")));
    return;
  }
  if (url.pathname.startsWith("/static/")) {
    // רשת קודם (קוד תמיד עדכני), מטמון כגיבוי כשאין רשת
    e.respondWith(fetch(e.request).then((r) => {
      if (r.ok) { const copy = r.clone(); caches.open(VERSION).then((c) => c.put(e.request, copy)); }
      return r;
    }).catch(() => caches.match(e.request)));
  }
});
