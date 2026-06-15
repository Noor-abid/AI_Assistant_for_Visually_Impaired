const CACHE = "assistive-vision-v4";
const ASSETS = [
  "/",
  "/static/css/main.css",
  "/static/js/main.js",
  "/static/js/config.js",
  "/static/js/haptics.js",
  "/static/js/input.js",
  "/static/js/localVision.js",
  "/static/js/network.js",
  "/static/js/speech.js",
  "/static/js/ui.js"
];

self.addEventListener("install", (event) => {
  self.skipWaiting();
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(ASSETS)));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
