"""FastAPI uçları: POST /ai/chat (akış) ve POST /ai/chart-read.

Kişi 2 main.py'de ekler:
    from app.ai.router import router as ai_router
    app.include_router(ai_router)
"""
from __future__ import annotations

import json
import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .chart_read import read_chart
from .chat import ChatRequest, chat_once, chat_stream
from .context import AnalysisSource, NullAnalysisSource
from .provider import get_provider
from .rag import get_retriever

# Kimlik doğrulama Kişi 2'nin backend/app/core modülünden gelir (değiştirmeden import).
# O modül henüz yoksa geliştirme sırasında anonim kullanıcıya izin verilir.
try:  # pragma: no cover
    from app.core.auth import get_current_user  # type: ignore
except ImportError:  # pragma: no cover

    async def get_current_user() -> dict[str, Any]:
        return {"id": "dev-anon"}


_SOURCE: AnalysisSource | None = None


def get_analysis_source() -> AnalysisSource:
    """Veritabanı varsa (asıl backend) DbAnalysisSource; yoksa (yerel dev_server) NullAnalysisSource."""
    global _SOURCE
    if _SOURCE is None:
        try:
            from .db import DbAnalysisSource

            _SOURCE = DbAnalysisSource.from_app()
        except Exception as e:  # sqlalchemy / DATABASE_URL yok → veri olmadan çalış
            logger.info("Veritabanı kaynağı yok, analiz verisi olmadan çalışılıyor: %r", e)
            _SOURCE = NullAnalysisSource()
    return _SOURCE


logger = logging.getLogger("app.ai")
router = APIRouter(prefix="/ai", tags=["ai"])


class Msg(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class Ctx(BaseModel):
    screen: str | None = None
    code: str | None = None
    horizon: int | None = None


class ChatBody(BaseModel):
    messages: list[Msg] = Field(min_length=1, max_length=40)
    image: str | None = None
    context: Ctx | None = None


class ChartReadBody(BaseModel):
    image: str
    code: str | None = None


def friendly_error(e: Exception) -> tuple[int, str]:
    """Sağlayıcı hatasını (HTTP kodu, kullanıcıya gösterilecek Türkçe mesaj) çiftine çevirir."""
    if "Timeout" in type(e).__name__:
        return 504, "Yapay zekâ zamanında yanıt vermedi. Biraz sonra tekrar deneyin."
    status = getattr(getattr(e, "response", None), "status_code", None)
    if status == 429:
        return 429, "Ücretsiz kullanım sınırına ulaşıldı. Bir dakika sonra tekrar deneyin."
    if status in (401, 403):
        return 502, "API anahtarı geçersiz ya da eksik (backend/.env)."
    if status == 404:
        return 502, "Model bulunamadı ya da bu anahtarla kullanılamıyor (backend/.env → GEMINI_MODEL)."
    if status in (500, 502, 503, 504):
        return 503, "Yapay zekâ servisi şu an yoğun. Birkaç saniye sonra tekrar deneyin."
    return 502, "Yanıt üretilemedi, biraz sonra tekrar deneyin."


@router.post("/chat")
async def chat(
    body: ChatBody,
    request: Request,
    _user: dict = Depends(get_current_user),
    source: AnalysisSource = Depends(get_analysis_source),
):
    req = ChatRequest(
        messages=[m.model_dump() for m in body.messages],
        image=body.image,
        context=body.context.model_dump(exclude_none=True) if body.context else None,
    )
    provider = get_provider()
    retriever = get_retriever()

    # İstemci akış istemiyorsa (ör. eski sürüm) tek parça JSON
    if "text/event-stream" not in request.headers.get("accept", ""):
        try:
            return {"reply": await chat_once(req, provider, retriever, source)}
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e

    async def events():
        try:
            async for ev in chat_stream(req, provider, retriever, source):
                payload: dict[str, Any] = {}
                if ev.delta:
                    payload["delta"] = ev.delta
                if ev.done:
                    payload["done"] = True
                    payload["sources"] = ev.sources
                if ev.replace is not None:
                    payload["replace"] = ev.replace
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        except ValueError as e:
            yield f"data: {json.dumps({'error': str(e), 'done': True}, ensure_ascii=False)}\n\n"
        except Exception as e:  # sağlayıcı hatası: ayrıntıyı istemciye sızdırma, sunucu günlüğüne yaz
            _, msg = friendly_error(e)
            logger.warning("AI sağlayıcı hatası: %r", e)
            yield f"data: {json.dumps({'error': msg, 'done': True}, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.post("/chart-read")
async def chart_read(
    body: ChartReadBody,
    _user: dict = Depends(get_current_user),
    source: AnalysisSource = Depends(get_analysis_source),
):
    try:
        return await read_chart(body.image, body.code, get_provider(), source)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:  # sağlayıcı hatası → anlaşılır mesaj (önceden düz 500 dönüyordu)
        code, msg = friendly_error(e)
        logger.warning("AI grafik okuma hatası: %r", e)
        raise HTTPException(status_code=code, detail=msg) from e
