"""Yanıt süresi ölçümü (Görev 10): her yanıta Server-Timing başlığı + günlüğe bir satır.

  Server-Timing: app;dur=12.3        (tarayıcı geliştirici araçlarında ve curl -i ile görünür)
  günlük: "GET /assets 200 12.3ms"   (Render → Logs; tezdeki yanıt süresi tablosu buradan da çıkarılabilir)

Ölçülen süre sunucu içi işlem süresidir (ağ gecikmesi hariç). Uçtan uca süre için
backend/scripts/olc_yanit_suresi.py kullanılır.
"""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware

log = logging.getLogger("api.timing")


class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        t0 = time.perf_counter()
        response = await call_next(request)
        ms = (time.perf_counter() - t0) * 1000
        response.headers["Server-Timing"] = f"app;dur={ms:.1f}"
        if request.url.path != "/health":
            # Yol şablonu (ör. /assets/{code}/analysis) varsa onu yaz: kişisel veri/kod günlüğe dağılmasın
            route = request.scope.get("route")
            path = getattr(route, "path", request.url.path)
            log.info("%s %s %s %.1fms", request.method, path, response.status_code, ms)
        return response
