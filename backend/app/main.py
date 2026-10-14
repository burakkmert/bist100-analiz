"""FastAPI uygulamasının giriş noktası.

Çalıştırma (repo kökünden):  docker compose up
Yerelde (backend/ içinde):   uvicorn app.main:app --reload
Belgeler:                    http://localhost:8000/docs

Sözleşme: shared/openapi.yaml (Hafta 2'de eklenecek), shared/db_schema.sql
"""

import json
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.exc import OperationalError

from app.ai.router import router as ai_router  # Kişi 3 — prefix="/ai" router'ın içinde
from app.api import assets, backtest, devices, health, paper, portfolio, profile, signals
from app.core.config import get_settings
from app.core.ratelimit import RateLimitMiddleware
from app.core.timing import TimingMiddleware

settings = get_settings()

# Kendi günlüklerimiz (ör. api.timing) uvicorn'unkilerle birlikte görünsün
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="Fon ve Hisse Takip API",
    version="0.2.0",
    description="Model sinyalleri yatırım tavsiyesi değildir (SPK).",
)

# İstek sınırı CORS'tan ÖNCE eklenir: Starlette'te son eklenen en dışta çalışır, böylece 429 yanıtları da
# CORS başlıklarını taşır (tarayıcı/Expo web hatayı okuyabilsin).
app.add_middleware(TimingMiddleware)  # en içte: yalnızca uygulamanın kendi süresini ölçer

app.add_middleware(
    RateLimitMiddleware,
    per_min=settings.rate_limit_per_min,
    ai_per_min=settings.rate_limit_ai_per_min,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------- hata yönetimi
# Beklenmeyen hatalar istemciye iç ayrıntı sızdırmadan, her zaman JSON ve Türkçe döner;
# ayrıntı günlüğe yazılır.
log = logging.getLogger("api.errors")


@app.exception_handler(OperationalError)
async def db_unavailable(request: Request, exc: OperationalError):
    """Veritabanına ulaşılamıyor (ör. Supabase duraklatıldı, bağlantı koptu) → 503, tekrar denenebilir."""
    log.error("Veritabanı hatası: %s %s: %s", request.method, request.url.path, exc.__class__.__name__)
    return JSONResponse(
        {"detail": "Veritabanına şu an ulaşılamıyor. Biraz sonra tekrar deneyin."},
        status_code=503,
        headers={"Retry-After": "30"},
    )


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    log.exception("Beklenmeyen hata: %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "Beklenmeyen bir sunucu hatası oluştu."}, status_code=500)


app.include_router(health.router)
app.include_router(profile.router)
app.include_router(devices.router)  # piyasa verisine bağlı değil; MOCK=1'de de gerçek
app.include_router(ai_router)


# Piyasa verisine dayanan uçlar (/assets, /screener, /backtest/summary) ve varlık koduna bağlı
# kullanıcı kayıtları (/portfolio, /watchlist: assets tablosuna yabancı anahtar) gerçek veritabanıyla
# yalnızca MOCK=0 iken çalışır. MOCK=1 iken aynı uçlar sözleşme örnekleriyle cevap verir
# (veritabanı boşken mobil boş ekran görmesin).
if not settings.mock:
    app.include_router(assets.router)
    app.include_router(portfolio.router)
    app.include_router(backtest.router)
    app.include_router(signals.router)
    app.include_router(paper.router)

# MOCK=1: sözleşmede olup henüz yazılmamış uçlar openapi.yaml örnekleriyle cevap verir.
# Gerçek router'lardan SONRA çağrılmalı ki yazılmış uçları ezmesin.
if settings.mock:
    from app.api.mock import register_mock_routes

    register_mock_routes(app)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


# ---------------------------------------------------------------------------
# GEÇİCİ: ilk iskeletten kalan sahte uçlar (backend/mock/*.json).
# Sözleşmedeki /assets uçları gelince (Hafta 3–4) kaldırılacak.
# ---------------------------------------------------------------------------
MOCK_DIR = Path(__file__).resolve().parent.parent / "mock"


def _load_mock(name: str):
    path = MOCK_DIR / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Veri bulunamadı")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/stocks", tags=["eski-mock"], deprecated=True)
def list_stocks():
    return _load_mock("stocks.json")


@app.get("/stocks/{symbol}/analysis", tags=["eski-mock"], deprecated=True)
def stock_analysis(symbol: str):
    return _load_mock(f"analysis_{symbol.upper()}.json")
