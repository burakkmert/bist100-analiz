"""FastAPI iskeleti. Şimdilik sahte veriyle çalışır; karar motoru hazır olunca
`backend/mock/` yerine veritabanından okunacak. Sözleşme: docs/api.md
"""
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

MOCK = Path(__file__).resolve().parent.parent / "mock"

app = FastAPI(title="BIST100 Analiz API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])


def _load(name: str):
    path = MOCK / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Veri bulunamadı")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stocks")
def list_stocks():
    return _load("stocks.json")


@app.get("/stocks/{symbol}/analysis")
def stock_analysis(symbol: str):
    return _load(f"analysis_{symbol.upper()}.json")
