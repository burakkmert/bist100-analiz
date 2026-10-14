"""İstek sınırı (rate limit): kullanıcı başına dakikada en fazla N istek.

  * Genel uçlar   : RATE_LIMIT_PER_MIN    (varsayılan 120/dk)
  * /ai/* uçları  : RATE_LIMIT_AI_PER_MIN (varsayılan 10/dk) — her istek bir LLM çağrısı, ücretli/kotalı
  * /health ve /docs sınırsız. 0 = kapalı.

Anahtar: Authorization başlığındaki token (özeti) → aynı kullanıcı; token yoksa istemci IP'si.
Token burada DOĞRULANMAZ (doğrulama get_current_user'da); sahte token üretmek yalnızca kendi
kotasını ayırır, başkasınınkini tüketmez.

Sınır aşılınca 429 + Retry-After. Sayaçlar bellekte tutulur (tek süreç; birden çok worker'da her
worker kendi sayacını tutar — proje ölçeğinde yeterli, gerekirse Redis'e taşınır).
"""

from __future__ import annotations

import hashlib
import math
import time
from collections import deque
from collections.abc import Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

WINDOW = 60.0
EXEMPT = ("/health", "/docs", "/openapi.json", "/redoc")


class SlidingWindow:
    """Anahtar başına son WINDOW saniyedeki istek zamanları."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self.hits: dict[str, deque[float]] = {}
        self._last_sweep = clock()

    def hit(self, key: str, limit: int) -> float | None:
        """İsteği say. İzin varsa None, yoksa kaç saniye sonra tekrar denenebileceği."""
        now = self.clock()
        q = self.hits.setdefault(key, deque())
        while q and q[0] <= now - WINDOW:
            q.popleft()
        if len(q) >= limit:
            return max(q[0] + WINDOW - now, 0.0)
        q.append(now)
        self._sweep(now)
        return None

    def _sweep(self, now: float) -> None:
        """Boşalmış anahtarları arada bir temizle (bellek sızmasın)."""
        if now - self._last_sweep < WINDOW:
            return
        self._last_sweep = now
        for k in [k for k, q in self.hits.items() if not q or q[-1] <= now - WINDOW]:
            del self.hits[k]


def client_key(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer ") and len(auth) > 7:
        return "u:" + hashlib.sha256(auth[7:].encode()).hexdigest()[:24]
    return "ip:" + (request.client.host if request.client else "?")


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, per_min: int, ai_per_min: int, window: SlidingWindow | None = None):
        super().__init__(app)
        self.per_min, self.ai_per_min = per_min, ai_per_min
        self.window = window or SlidingWindow()

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method == "OPTIONS" or path == "/" or path.startswith(EXEMPT):
            return await call_next(request)
        is_ai = path.startswith("/ai/")
        limit = self.ai_per_min if is_ai else self.per_min
        if limit > 0:
            key = ("ai|" if is_ai else "") + client_key(request)
            wait = self.window.hit(key, limit)
            if wait is not None:
                retry = max(1, math.ceil(wait))
                return JSONResponse(
                    {"detail": f"Çok fazla istek. {retry} saniye sonra tekrar deneyin."},
                    status_code=429,
                    headers={"Retry-After": str(retry)},
                )
        return await call_next(request)
