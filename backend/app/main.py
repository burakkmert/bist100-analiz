"""FastAPI uygulamasının giriş noktası.

Çalıştırma (repo kökünden):  docker compose up
Yerelde (backend/ içinde):   uvicorn app.main:app --reload
Belgeler:                    http://localhost:8000/docs

Sözleşme: shared/openapi.yaml (Hafta 2'de eklenecek), shared/db_schema.sql
"""

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.ai.router import router as ai_router  # Kişi 3 — prefix="/ai" router'ın içinde
from app.api import assets, backtest, devices, health, portfolio, profile, signals
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="Fon ve Hisse Takip API",
    version="0.2.0",
    description="Model sinyalleri yatırım tavsiyesi değildir (SPK).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
