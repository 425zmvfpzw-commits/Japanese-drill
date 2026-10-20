// 오프라인용: 앱 파일과 드릴 음성은 폰에 저장해 두고, 인터넷이 있으면 조용히 새 버전으로 바꿉니다.
const CACHE = "nihongo-a6f86cecb9", AUDIO = "drill-audio";
const SHELL = ["./", "index.html", "manifest.webmanifest", "icons/icon-192.png", "icons/icon-512.png", "icons/apple-touch-icon.png"];
self.addEventListener("install", e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener("activate", e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k.startsWith("nihongo-") && k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
// 아이폰은 음성 파일을 조각(Range)으로 달라고 하므로, 저장된 파일에서 그 조각을 잘라 준다
async function audioResponse(req) {
  const url = req.url.split("#")[0];
  const c = await caches.open(AUDIO);
  let full = await c.match(url);
  if (!full) {
    try { const r = await fetch(url); if (r.ok) { await c.put(url, r.clone()); full = r; } else return r; }
    catch (e) { return new Response("", {status: 504}); }
  }
  const range = req.headers.get("range");
  if (!range) return full;
  const buf = await full.clone().arrayBuffer(), size = buf.byteLength;
  const m = /bytes=(\d*)-(\d*)/.exec(range) || [];
  let start = m[1] ? parseInt(m[1], 10) : 0, end = m[2] ? parseInt(m[2], 10) : size - 1;
  if (!m[1] && m[2]) { start = size - parseInt(m[2], 10); end = size - 1; }
  end = Math.min(end, size - 1);
  return new Response(buf.slice(start, end + 1), {status: 206, headers: {
    "Content-Type": "audio/mpeg", "Content-Range": `bytes ${start}-${end}/${size}`,
    "Content-Length": String(end - start + 1), "Accept-Ranges": "bytes" }});
}
self.addEventListener("fetch", e => {
  const req = e.request; if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin === location.origin && /\/audio\/[a-z0-9_-]+\/[0-9a-f]{16}\.mp3$/.test(url.pathname)) { e.respondWith(audioResponse(req)); return; }
  const isFont = /fonts\.(googleapis|gstatic)\.com$/.test(url.hostname);
  const isLib = url.hostname === "cdnjs.cloudflare.com";
  if (url.origin !== location.origin && !isFont && !isLib) return;
  e.respondWith(caches.open(CACHE).then(async c => {
    const hit = await c.match(req, {ignoreSearch: url.origin === location.origin});
    const net = fetch(req).then(r => { if (r && (r.ok || r.type === "opaque")) c.put(req, r.clone()); return r; }).catch(() => hit || new Response("", {status: 504}));
    return hit || net;
  }));
});
