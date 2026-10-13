"""OpenAI uyumlu Chat Completions API'leri için adaptör (DeepSeek, OpenAI, OpenRouter, yerel vLLM...).

Ortam değişkenleri (örnek: DeepSeek):
    LLM_PROVIDER=deepseek
    DEEPSEEK_API_KEY=sk-...                      # platform.deepseek.com → API Keys
    DEEPSEEK_MODEL=deepseek-v4-flash             # metin/sohbet modeli
    DEEPSEEK_VISION_MODEL=deepseek-v4-flash-vision-exp   # görsel destekli model (grafik okuma); boşsa görsel kapalı

Model adları değişebilir; güncel adları sağlayıcının belgelerinden kontrol edin.
API anahtarı yalnızca sunucuda durur, mobil uygulamaya asla konmaz.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import time
from typing import AsyncIterator

import httpx

from .provider import register

log = logging.getLogger("app.ai.gemini")


class OpenAICompatProvider:
    name = "openai-compat"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        vision_model: str | None = None,
        timeout: float = 60.0,
        temperature: float = 0.3,
    ):
        if not api_key:
            raise ValueError(f"{self.name}: API anahtarı tanımlı değil.")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.vision_model = vision_model or None
        self.supports_images = bool(self.vision_model)
        self.temperature = temperature
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(timeout, connect=10.0),
        )

    @staticmethod
    def _messages(system: str, messages: list[dict], images: list[bytes] | None) -> list[dict]:
        out: list[dict] = [{"role": "system", "content": system}]
        out += [{"role": m["role"], "content": m["content"]} for m in messages]
        if images:
            # Görseller son kullanıcı mesajına eklenir (OpenAI "image_url" biçimi, data URI ile)
            last = out[-1]
            parts: list[dict] = [{"type": "text", "text": last["content"]}]
            for img in images:
                mime = "image/png" if img[:4] == b"\x89PNG" else "image/jpeg"
                b64 = base64.b64encode(img).decode()
                parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
            last["content"] = parts
        return out

    async def complete(self, system: str, messages: list[dict], images: list[bytes] | None = None) -> str:
        if images and not self.supports_images:
            raise ValueError("Seçili model görsel desteklemiyor.")
        r = await self._client.post(
            "/chat/completions",
            json={
                "model": self.vision_model if images else self.model,
                "messages": self._messages(system, messages, images),
                "temperature": self.temperature,
                "stream": False,
            },
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"] or ""

    async def stream(self, system: str, messages: list[dict]) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "messages": self._messages(system, messages, None),
            "temperature": self.temperature,
            "stream": True,
        }
        async with self._client.stream("POST", "/chat/completions", json=payload) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    delta = json.loads(data)["choices"][0]["delta"].get("content")
                except (KeyError, IndexError, json.JSONDecodeError):
                    continue
                if delta:
                    yield delta


class DeepSeekProvider(OpenAICompatProvider):
    name = "deepseek"

    def __init__(self):
        super().__init__(
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            vision_model=os.getenv("DEEPSEEK_VISION_MODEL", ""),
        )


register("deepseek", DeepSeekProvider)


def gemini_contents(messages: list[dict], images: list[bytes] | None) -> list[dict]:
    """Sohbet geçmişini Gemini'nin kendi biçimine çevirir (assistant → model, görseller inlineData)."""
    contents: list[dict] = []
    for m in messages:
        role = "model" if m["role"] == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})
    if images and contents:
        for img in images:
            mime = "image/png" if img[:4] == b"\x89PNG" else "image/jpeg"
            contents[-1]["parts"].append({"inlineData": {"mimeType": mime, "data": base64.b64encode(img).decode()}})
    return contents


def gemini_text(payload: dict) -> str:
    """Gemini yanıtından metni çıkarır (akıştaki her parça için de aynı)."""
    out = []
    for cand in payload.get("candidates") or []:
        for part in (cand.get("content") or {}).get("parts") or []:
            if part.get("text") and not part.get("thought"):
                out.append(part["text"])
    return "".join(out)


# Kotası dolan modeller: {model: tekrar denenebileceği zaman (epoch sn)}. Süreç boyunca paylaşılır
# (get_provider her istekte yeni nesne üretir, bu yüzden modül düzeyinde tutulur).
_GEMINI_COOLDOWN: dict[str, float] = {}
_SWITCH_STATUSES = {404, 429, 500, 502, 503, 504}


# Zaman aşımı istisnaları (testlerde httpx taklit edilebildiği için getattr)
_TIMEOUTS: tuple[type[BaseException], ...] = (TimeoutError,) + tuple(
    t for t in (getattr(httpx, "TimeoutException", None),) if t
)


def _cooldown_seconds(status: int, body: str) -> float:
    """Hangi modeli ne kadar süre atlayacağımız."""
    if status == 429:
        return 6 * 3600 if "PerDay" in body else 65  # günlük kota → saatlerce; dakikalık → ~1 dk
    if status == 404:
        return 24 * 3600  # model yok/erişilemiyor
    return 30  # 5xx: geçici yoğunluk


def _parse_models(value: str | None, default: str) -> list[str]:
    models = [m.strip() for m in (value or default).split(",") if m.strip()]
    return list(dict.fromkeys(models))  # tekrarları at, sırayı koru


class GeminiProvider:
    """Google Gemini — Google'ın kendi API'si (generateContent). Ücretsiz katmanı var.

    Model sırası: GEMINI_MODEL virgülle birden çok model alabilir. Ücretsiz katmanda kota model başına
    sayıldığı için, bir model "kota doldu" (429), "bulunamadı" (404) ya da "yoğun" (5xx) derse otomatik
    olarak sıradakine geçilir; kotası dolan model bir süre atlanır.
        GEMINI_MODEL=gemini-3.5-flash,gemini-3.8-flash,gemini-3.1-flash-lite

    Not: OpenAI uyumlu uç (/v1beta/openai) bazı yeni anahtar türlerinde 404 verdiği için kendi API kullanılır.
    Ücretsiz katmanda gönderilen içerik Google tarafından ürün geliştirmede kullanılabilir; kişisel veri göndermeyin.
    """

    name = "gemini"

    def __init__(self):
        key = os.getenv("GEMINI_API_KEY", "")
        if not key:
            raise ValueError("gemini: GEMINI_API_KEY tanımlı değil (backend/.env).")
        self.models = _parse_models(os.getenv("GEMINI_MODEL"), "gemini-3.5-flash")
        self.vision_models = _parse_models(os.getenv("GEMINI_VISION_MODEL"), ",".join(self.models))
        self.model = self.models[0]  # geriye uyumluluk
        self.last_model: str | None = None  # son başarılı çağrıda kullanılan model
        self.supports_images = True
        self.temperature = 0.3
        self._client = httpx.AsyncClient(
            base_url=os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"),
            # Anahtar adres parametresiyle (?key=) gönderilir: bazı yeni anahtar türleri (AQ. ile başlayanlar)
            # x-goog-api-key başlığıyla 404 döndürüyor, ?key= ile çalışıyor.
            params={"key": key},
            timeout=httpx.Timeout(90.0, connect=10.0),
        )

    @staticmethod
    def _candidates(models: list[str]) -> list[str]:
        now = time.time()
        ready = [m for m in models if _GEMINI_COOLDOWN.get(m, 0) <= now]
        return ready or models  # hepsi beklemedeyse yine de sırayla dene (kota sıfırlanmış olabilir)

    @staticmethod
    def _mark(model: str, status: int, body: str) -> None:
        _GEMINI_COOLDOWN[model] = time.time() + _cooldown_seconds(status, body)
        log.warning("Gemini %s atlanıyor (HTTP %s); sıradaki modele geçiliyor", model, status)

    def _body(self, system: str, messages: list[dict], images: list[bytes] | None) -> dict:
        return {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": gemini_contents(messages, images),
            "generationConfig": {"temperature": self.temperature},
        }

    async def complete(self, system: str, messages: list[dict], images: list[bytes] | None = None) -> str:
        """Sırayla modelleri dener. Toplam süre GEMINI_TOTAL_TIMEOUT'u (vars. 75 sn) aşmaz; böylece
        telefon beklemeyi kesmeden önce ya cevap ya da anlaşılır bir hata döner. Takılan (zaman aşımı)
        model de kota dolmuş gibi kısa süre atlanır ve sıradakine geçilir."""
        body = self._body(system, messages, images)
        last_error: Exception | None = None
        deadline = time.monotonic() + float(os.getenv("GEMINI_TOTAL_TIMEOUT", "75"))
        per_try = float(os.getenv("GEMINI_TRY_TIMEOUT", "40"))
        for model in self._candidates(self.vision_models if images else self.models):
            left = deadline - time.monotonic()
            if left < 5:
                break
            try:
                r = await self._client.post(f"/models/{model}:generateContent", json=body, timeout=min(per_try, left))
            except _TIMEOUTS as e:
                self._mark(model, 504, "timeout")
                last_error = e
                continue
            if r.status_code in _SWITCH_STATUSES:
                self._mark(model, r.status_code, r.text)
                last_error = httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
                continue
            r.raise_for_status()
            self.last_model = model
            log.info("Gemini yanıtı: %s%s", model, " (görselli)" if images else "")
            return gemini_text(r.json())
        if last_error is None:
            last_error = TimeoutError("Gemini: süre doldu")
        raise last_error

    async def stream(self, system: str, messages: list[dict]) -> AsyncIterator[str]:
        body = self._body(system, messages, None)
        last_error: Exception | None = None
        for model in self._candidates(self.models):
            url = f"/models/{model}:streamGenerateContent"
            async with self._client.stream("POST", url, params={"alt": "sse"}, json=body) as r:
                if r.status_code in _SWITCH_STATUSES:
                    text = (await r.aread()).decode("utf-8", "replace")
                    self._mark(model, r.status_code, text)
                    last_error = httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
                    continue  # henüz hiç metin gönderilmedi; sıradaki modeli dene
                r.raise_for_status()
                self.last_model = model
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        text = gemini_text(json.loads(line[5:].strip()))
                    except json.JSONDecodeError:
                        continue
                    if text:
                        yield text
                return
        assert last_error is not None
        raise last_error


class OllamaProvider(OpenAICompatProvider):
    """Bilgisayarda yerel çalışan modeller (Ollama) — tamamen ücretsiz, internet/anahtar gerekmez."""

    name = "ollama"

    def __init__(self):
        super().__init__(
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
            api_key="ollama",  # Ollama anahtar istemez ama başlık dolu olmalı
            model=os.getenv("OLLAMA_MODEL", "qwen2.5vl:7b"),
            vision_model=os.getenv("OLLAMA_VISION_MODEL", os.getenv("OLLAMA_MODEL", "qwen2.5vl:7b")),
            timeout=180.0,
        )


register("gemini", GeminiProvider)
register("ollama", OllamaProvider)
