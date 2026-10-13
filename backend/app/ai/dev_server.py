"""Geliştirme sunucusu: yalnızca yapay zekâ uçlarını çalıştırır.

Kişi 2'nin asıl backend'i (main.py) hazır olana kadar asistanı gerçek LLM ile denemek için.
Çalıştırma (backend/ klasöründen):
    uvicorn app.ai.dev_server:app --host 0.0.0.0 --port 8000
Ayarlar backend/.env dosyasından okunur (LLM_PROVIDER, GEMINI_API_KEY ...).
"""
from __future__ import annotations

from .settings import load_env  # noqa: E402

load_env()


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
