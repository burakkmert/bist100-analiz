"""İstek sınırı: kullanıcı başına pencere, /ai/* daha sıkı, 429 + Retry-After, muaf yollar."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.ratelimit import RateLimitMiddleware, SlidingWindow


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _app(per_min=3, ai_per_min=1):
    clock = Clock()
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware, per_min=per_min, ai_per_min=ai_per_min, window=SlidingWindow(clock)
    )

    @app.get("/assets")
    def assets():
        return []

    @app.post("/ai/chat")
    def chat():
        return {}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return TestClient(app), clock


A = {"Authorization": "Bearer token-a"}
B = {"Authorization": "Bearer token-b"}


def test_sinir_asilinca_429_ve_retry_after():
    c, clock = _app()
    assert [c.get("/assets", headers=A).status_code for _ in range(3)] == [200, 200, 200]
    r = c.get("/assets", headers=A)
    assert r.status_code == 429 and r.headers["Retry-After"] == "60"
    assert "saniye" in r.json()["detail"]
    clock.t += 30
    assert c.get("/assets", headers=A).headers["Retry-After"] == "30"
    clock.t += 31  # ilk istekler pencereden çıktı
    assert c.get("/assets", headers=A).status_code == 200


def test_kullanicilar_birbirini_etkilemez():
    c, _ = _app()
    for _ in range(3):
        c.get("/assets", headers=A)
    assert c.get("/assets", headers=A).status_code == 429
    assert c.get("/assets", headers=B).status_code == 200
    assert c.get("/assets").status_code == 200  # tokensız → IP anahtarı


def test_ai_uclari_ayri_ve_daha_siki():
    c, _ = _app()
    assert c.post("/ai/chat", headers=A).status_code == 200
    assert c.post("/ai/chat", headers=A).status_code == 429
    assert c.get("/assets", headers=A).status_code == 200  # genel kota ayrı


def test_health_muaf_ve_sifir_kapali():
    c, _ = _app(per_min=1)
    assert all(c.get("/health").status_code == 200 for _ in range(5))
    c0, _ = _app(per_min=0, ai_per_min=0)
    assert all(c0.get("/assets", headers=A).status_code == 200 for _ in range(10))


def test_bos_anahtarlar_temizlenir():
    clock = Clock()
    w = SlidingWindow(clock)
    w.hit("x", 5)
    clock.t += 61
    w.hit("y", 5)
    assert "x" not in w.hits and "y" in w.hits
