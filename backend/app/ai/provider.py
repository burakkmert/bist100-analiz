"""LLM sağlayıcı arayüzü.

Tüm LLM çağrıları bu arayüzden geçer; böylece model seçimi (6. hafta) kodu değiştirmez.
Sağlayıcı `.env`'deki LLM_PROVIDER ile seçilir. Model seçilene kadar `fake` kullanılır.
"""
from __future__ import annotations

import asyncio
import os
import re
from typing import AsyncIterator, Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    supports_images: bool

    async def complete(self, system: str, messages: list[dict], images: list[bytes] | None = None) -> str: ...

    async def stream(self, system: str, messages: list[dict]) -> AsyncIterator[str]: ...


class FakeProvider:
    """Sabit/kurallı cevap dönen sağlayıcı — geliştirme ve testler için.

    Gerçek bir modelin yerine geçmez; istemdeki "İLGİLİ SÖZLÜK MADDELERİ" ve "EKRAN BAĞLAMI"
    bölümlerini okuyup bunlardan kısa bir Türkçe cevap kurar. Böylece RAG ve bağlam
    hattının uçtan uca çalıştığı LLM olmadan da görülebilir.
    """

    name = "fake"
    supports_images = True

    def __init__(self, chunk_delay: float = 0.0):
        self.chunk_delay = chunk_delay

    async def complete(self, system: str, messages: list[dict], images: list[bytes] | None = None) -> str:
        if '"trend"' in system and "JSON" in system:  # grafik okuma istemi
            return _FAKE_CHART_JSON
        if "varlık yorumları yazan" in system:  # gece uzman yorumu istemi
            body = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
            lines = [l for l in body.splitlines() if l.startswith(("Ufuk:", "Güven skoru:", "%80"))]
            return "Model özeti (FakeProvider): " + " ".join(lines)
        user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        return _fake_answer(system, user, has_image=bool(images))

    async def stream(self, system: str, messages: list[dict]) -> AsyncIterator[str]:
        text = await self.complete(system, messages)
        # Kelime kelime gönder (boşlukları koruyarak) → istemcide "yazıyor" etkisi
        for part in re.findall(r"\S+\s*", text):
            if self.chunk_delay:
                await asyncio.sleep(self.chunk_delay)
            yield part


def _section(system: str, title: str) -> str:
    m = re.search(rf"### {re.escape(title)}\n(.*?)(?=\n### |\Z)", system, re.S)
    return m.group(1).strip() if m else ""


def _fake_answer(system: str, user: str, has_image: bool) -> str:
    glossary = _section(system, "İLGİLİ SÖZLÜK MADDELERİ")
    context = _section(system, "EKRAN BAĞLAMI")
    parts: list[str] = []
    if has_image:
        parts.append("Görseli aldım. (FakeProvider — gerçek görsel yorumu LLM seçilince çalışacak.)")
    if glossary:
        first = glossary.split("\n\n")[0]
        name = re.search(r"^\[(.+?)\]", first, re.M)
        tanim = re.search(r"Tanım: (.+)", first)
        if name and tanim:
            parts.append(f"{name.group(1)}: {tanim.group(1)}")
    if context and "veri yok" not in context:
        parts.append("Bu ekrandaki model verisine göre: " + context.splitlines()[0])
    if not parts:
        parts.append(
            "Bu soruyu yanıtlamak için yeterli bilgim yok. Bir terim sorabilir ya da ekran görüntüsü gönderebilirsiniz."
        )
    parts.append("Bu bir model yorumudur, yatırım tavsiyesi değildir.")
    return "\n\n".join(parts)


_FAKE_CHART_JSON = (
    '{"trend": "up", "supports": [], "resistances": [], "pattern": null, '
    '"indicators_note": null, "summary": "Grafikte genel olarak yükselen bir eğilim görülüyor (FakeProvider örneği).", '
    '"confidence_note": "Yalnızca görsel desen yorumu; sayısal veriyle karşılaştırılmadı."}'
)


# ---- Fabrika -------------------------------------------------------------------------------------

_registry: dict[str, type] = {"fake": FakeProvider}
_LAZY = {"deepseek", "gemini", "ollama"}  # provider_openai.py içinde kayıtlı


def register(name: str, cls: type) -> None:
    """Gerçek sağlayıcı adaptörleri (karşılaştırmadan sonra) burada kaydedilir."""
    _registry[name] = cls


def get_provider(name: str | None = None) -> LLMProvider:
    key = (name or os.getenv("LLM_PROVIDER") or "fake").strip().lower()
    if key in _LAZY and key not in _registry:
        # Gerçek adaptörler httpx gerektirir; yalnızca seçildiğinde yüklenir (testler bağımlılıksız kalsın)
        from . import provider_openai  # noqa: F401
    if key not in _registry:
        raise ValueError(f"Bilinmeyen LLM_PROVIDER: {key!r}. Kayıtlı olanlar: {sorted(_registry)}")
    return _registry[key]()
