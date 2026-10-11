"""Geliştirme sunucusu: yalnızca yapay zekâ uçlarını çalıştırır.

Kişi 2'nin asıl backend'i (main.py) hazır olana kadar asistanı gerçek LLM ile denemek için.
Çalıştırma (backend/ klasöründen):
    uvicorn app.ai.dev_server:app --host 0.0.0.0 --port 8000
Ayarlar backend/.env dosyasından okunur (LLM_PROVIDER, GEMINI_API_KEY ...).
"""
from __future__ import annotations

import os
from pathlib import Path


def _load_env(path: Path) -> None:
    """python-dotenv gerektirmeden basit .env okuyucu (KEY=değer, # yorum)."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.split(" #", 1)[0].strip()  # satır sonu yorumu
        if "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env(Path(__file__).resolve().parents[2] / ".env")

from fastapi import FastAPI  # noqa: E402

from .provider import get_provider  # noqa: E402
from .router import router as ai_router  # noqa: E402

app = FastAPI(title="Fon Takip — AI geliştirme sunucusu")
app.include_router(ai_router)


@app.get("/health")
async def health():
    """Telefondan/tarayıcıdan bağlantıyı denemek için: http://<bilgisayar-ip>:8000/health"""
    try:
        p = get_provider()
        return {"ok": True, "provider": p.name, "vision": p.supports_images}
    except Exception as e:  # anahtar eksik vb.
        return {"ok": False, "error": str(e)}
