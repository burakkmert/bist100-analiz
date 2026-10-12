"""Ekran bağlamı: balonun açıldığı ekran ve varlık için modelin sayısal verisini isteme eklemek.

Sohbet ve grafik okuma, LLM'in uydurmaması (halüsinasyon) için varlığın gerçek analiz verisini
istemde görmelidir. Veriyi Kişi 2'nin veritabanından okuyan kaynak `DbAnalysisSource` olacak;
o hazır olana kadar `NullAnalysisSource` "veri yok" döner.
"""
from __future__ import annotations

from typing import Any, Protocol


class AnalysisSource(Protocol):
    async def get_analysis(self, code: str, horizon: int = 5) -> dict[str, Any] | None: ...

    async def get_recent_prices(self, code: str, days: int = 120) -> list[dict[str, Any]] | None: ...


class NullAnalysisSource:
    async def get_analysis(self, code: str, horizon: int = 5) -> dict[str, Any] | None:
        return None

    async def get_recent_prices(self, code: str, days: int = 120) -> list[dict[str, Any]] | None:
        return None


class StaticAnalysisSource:
    """Testler ve demo için: sözlükten verilen sabit veriyi döner."""

    def __init__(self, analyses: dict[str, dict[str, Any]], prices: dict[str, list[dict[str, Any]]] | None = None):
        self.analyses = analyses
        self.prices = prices or {}

    async def get_analysis(self, code: str, horizon: int = 5) -> dict[str, Any] | None:
        return self.analyses.get(code.upper())

    async def get_recent_prices(self, code: str, days: int = 120) -> list[dict[str, Any]] | None:
        p = self.prices.get(code.upper())
        return p[-days:] if p else None


SCREEN_NAMES = {
    "home": "Ana sayfa",
    "markets": "Piyasalar",
    "portfolio": "Portföy",
    "settings": "Ayarlar",
    "asset_detail": "Varlık detay",
}

_DIR = {"up": "yükseliş yönlü", "down": "düşüş yönlü", "flat": "yatay"}
_RISK = {"low": "düşük", "medium": "orta", "high": "yüksek"}
_REGIME = {"trend": "trend", "range": "yatay piyasa", "high_vol": "yüksek oynaklık"}


def describe(context: dict[str, Any] | None, analysis: dict[str, Any] | None) -> str:
    """Bağlamı istem için düz Türkçe satırlara çevirir. Sayılar olduğu gibi aktarılır."""
    if not context:
        return "Kullanıcı belirli bir ekrandan sormuyor (veri yok)."
    lines = [f"Kullanıcının bulunduğu ekran: {SCREEN_NAMES.get(context.get('screen', ''), context.get('screen', '?'))}"]
    code = context.get("code")
    if code:
        lines.insert(0, f"Varlık: {code}")
    if code and analysis:
        r = analysis.get("range") or {}
        ind = analysis.get("indicators") or {}
        lines += [
            f"Ufuk: {analysis.get('horizon')} gün · Model görüşü: {_DIR.get(analysis.get('direction', ''), analysis.get('direction'))}",
            f"Güven skoru: {analysis.get('confidence')}/100 · Risk: {_RISK.get(analysis.get('risk', ''), analysis.get('risk'))} · Rejim: {_REGIME.get(analysis.get('regime', ''), analysis.get('regime'))}",
            f"%80 olasılık aralığı (p10–p90): {r.get('low')} – {r.get('high')} · orta değer (p50): {r.get('mid')}",
        ]
        if ind:
            lines.append("Göstergeler: " + ", ".join(f"{k}={v}" for k, v in ind.items()))
        if analysis.get("weights"):
            lines.append("Model ağırlıkları: " + ", ".join(f"{k}={v}" for k, v in analysis["weights"].items()))
    elif code:
        lines.append("Bu varlık için model verisi şu an alınamadı (veri yok); sayı uydurma.")
    return "\n".join(lines)
