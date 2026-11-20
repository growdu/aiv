/* Service worker —— 只做一件事：让页面在网络不好的时候还能打开。
 *
 * 策略很简单：
 * - 导航请求（HTML）走「网络优先，失败回缓存」——有网时永远拿最新的；
 * - 其它静态资源走「缓存优先」——图片、样式、脚本不该每次都重下。
 *
 * 缓存名带一个版本号：改了前端资源就把版本号往上加一位，
 * 旧缓存会被 install 时的清理逻辑丢掉。
 */
const CACHE = 'site-v1';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== location.origin) return;

  const put = async (req, res) => {
    try {
      if (res && res.status === 200 && res.clone) {
        await caches.open(CACHE).then((cache) => cache.put(req, res.clone()));
      }
    } catch (_) {
      /* 缓存失败不影响这一次响应 */
    }
  };

  const isHtml = (request.headers.get('accept') || '').includes('text/html');

  if (isHtml) {
    event.respondWith(
      fetch(request)
        .then((res) => {
          put(request, res);
          return res;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  event.respondWith(
    caches.match(request).then(
      (hit) =>
        hit ||
        fetch(request)
          .then((res) => {
            put(request, res);
            return res;
          })
          .catch(() => caches.match(request))
    )
  );
});
