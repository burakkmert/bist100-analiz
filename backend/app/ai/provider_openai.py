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
import os
from typing import AsyncIterator

import httpx

from .provider import register


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


class GeminiProvider:
    """Google Gemini — Google'ın kendi API'si (generateContent). Ücretsiz katmanı var.

    Not: OpenAI uyumlu uç (/v1beta/openai) bazı yeni anahtar türlerinde 404 verdiği için kendi API kullanılır.
    Ücretsiz katmanda gönderilen içerik Google tarafından ürün geliştirmede kullanılabilir; kişisel veri göndermeyin.
    """

    name = "gemini"

    def __init__(self):
        key = os.getenv("GEMINI_API_KEY", "")
        if not key:
            raise ValueError("gemini: GEMINI_API_KEY tanımlı değil (backend/.env).")
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.vision_model = os.getenv("GEMINI_VISION_MODEL", self.model)
        self.supports_images = True
        self.temperature = 0.3
        self._client = httpx.AsyncClient(
            base_url=os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"),
            headers={"x-goog-api-key": key},
            timeout=httpx.Timeout(60.0, connect=10.0),
        )

    def _body(self, system: str, messages: list[dict], images: list[bytes] | None) -> dict:
        return {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": gemini_contents(messages, images),
            "generationConfig": {"temperature": self.temperature},
        }

    async def complete(self, system: str, messages: list[dict], images: list[bytes] | None = None) -> str:
        model = self.vision_model if images else self.model
        r = await self._client.post(f"/models/{model}:generateContent", json=self._body(system, messages, images))
        r.raise_for_status()
        return gemini_text(r.json())

    async def stream(self, system: str, messages: list[dict]) -> AsyncIterator[str]:
        url = f"/models/{self.model}:streamGenerateContent"
        async with self._client.stream("POST", url, params={"alt": "sse"}, json=self._body(system, messages, None)) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                try:
                    text = gemini_text(json.loads(line[5:].strip()))
                except json.JSONDecodeError:
                    continue
                if text:
                    yield text


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
