"""POST /ai/chat çekirdeği — FastAPI'den bağımsız, test edilebilir.

Akış: son kullanıcı mesajı → sözlükte ilgili terimler (RAG) → ekran bağlamı + analiz verisi →
sistem istemi → LLM (akış) → korkuluk kontrolü.
"""
from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator

from . import guardrails
from .context import AnalysisSource, NullAnalysisSource, describe
from .provider import LLMProvider
from .rag import Retriever

PROMPTS = Path(__file__).parent / "prompts"
MAX_HISTORY = 12
MAX_MESSAGE_CHARS = 2000
MAX_IMAGE_BYTES = 6 * 1024 * 1024


@dataclass
class ChatRequest:
    messages: list[dict[str, str]]
    image: str | None = None  # data URI
    context: dict[str, Any] | None = None


@dataclass
class ChatEvent:
    """İstemciye giden olay: metin parçası ya da bitiş (gerekirse düzeltilmiş tam metinle)."""

    delta: str = ""
    done: bool = False
    replace: str | None = None
    sources: list[str] = field(default_factory=list)


def load_prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8")


def clean_history(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    out = []
    for m in messages[-MAX_HISTORY:]:
        role = m.get("role")
        content = (m.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            out.append({"role": role, "content": content[:MAX_MESSAGE_CHARS]})
    if not out or out[-1]["role"] != "user":
        raise ValueError("Son mesaj kullanıcıdan gelmeli.")
    return out


def decode_image(data_uri: str | None) -> bytes | None:
    if not data_uri:
        return None
    m = re.match(r"^data:image/(png|jpe?g|webp|heic);base64,(.+)$", data_uri, re.S)
    if not m:
        raise ValueError("Görsel data:image/...;base64 biçiminde olmalı.")
    raw = base64.b64decode(m.group(2), validate=False)
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("Görsel çok büyük (en fazla 6 MB).")
    return raw


def build_system(context_text: str, glossary_chunks: list[str]) -> str:
    base = load_prompt("system_chat")
    gl = "\n\n".join(glossary_chunks) if glossary_chunks else "(ilgili madde bulunamadı)"
    return f"{base}\n\n### EKRAN BAĞLAMI\n{context_text}\n\n### İLGİLİ SÖZLÜK MADDELERİ\n{gl}\n"


async def prepare(req: ChatRequest, retriever: Retriever, source: AnalysisSource) -> tuple[str, list[dict], list[str]]:
    history = clean_history(req.messages)
    question = history[-1]["content"]
    hits = retriever.search(question, k=3)
    analysis = None
    ctx = req.context or None
    if ctx and ctx.get("code"):
        analysis = await source.get_analysis(str(ctx["code"]).upper(), int(ctx.get("horizon") or 5))
    system = build_system(describe(ctx, analysis), [t.as_chunk() for t, _ in hits])
    return system, history, [t.name for t, _ in hits]


async def chat_stream(
    req: ChatRequest,
    provider: LLMProvider,
    retriever: Retriever,
    source: AnalysisSource | None = None,
) -> AsyncIterator[ChatEvent]:
    system, history, sources = await prepare(req, retriever, source or NullAnalysisSource())
    image = decode_image(req.image)

    if image is not None:
        # Görselli istekler akışsız: çoğu sağlayıcı görseli yalnızca tam yanıtta destekler
        if not provider.supports_images:
            raise ValueError("Seçili model görsel desteklemiyor.")
        text = await provider.complete(system, history, images=[image])
        final = guardrails.sanitize(text)
        yield ChatEvent(delta=final, sources=sources)
        yield ChatEvent(done=True, sources=sources)
        return

    full = ""
    async for part in provider.stream(system, history):
        full += part
        yield ChatEvent(delta=part)
    final = guardrails.sanitize(full)
    if final == full:
        yield ChatEvent(done=True, sources=sources)
    elif final.startswith(full.rstrip()):
        # Yalnızca uyarı satırı eklendiyse kalanı parça olarak gönder
        yield ChatEvent(delta=final[len(full.rstrip()):])
        yield ChatEvent(done=True, sources=sources)
    else:
        # İhlal vardı: istemci metni bununla değiştirir
        yield ChatEvent(done=True, replace=final, sources=sources)


async def chat_once(req: ChatRequest, provider: LLMProvider, retriever: Retriever, source: AnalysisSource | None = None) -> str:
    """Akışsız tek parça cevap (MOCK istemciler ve testler için)."""
    text, replaced = "", None
    async for ev in chat_stream(req, provider, retriever, source):
        text += ev.delta
        if ev.replace is not None:
            replaced = ev.replace
    return replaced if replaced is not None else text
