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


# ---- Güven skorunun anlamı (Kişi 1 kalibrasyon bulgusu, backtest/summary/confidence_calibration.md) ----
# Karar motorunun ham güven skoru hisselerde isabeti ayırt etmiyor (90–100 güvenli sinyaller de ~%57 tutuyor).
# Yalnızca fonlarda 5 ve 20 günlük YUKARI sinyallerde anlamlı. Diğer durumlarda metinler "yüksek güven"
# demez; "yön sinyali zayıf, belirsizlik yüksek" dili kullanılır. Kişi 2 güveni "geçmişte benzer sinyallerin
# %X'i gerçekleşti" biçimine çevirince o oran (hit_rate) varsa onu kullanırız.


def confidence_is_informative(a: dict[str, Any] | None) -> bool:
    if not a:
        return False
    return a.get("asset_type") == "fund" and int(a.get("horizon") or 0) in (5, 20) and a.get("direction") == "up"


def hit_rate_pct(a: dict[str, Any] | None) -> int | None:
    """Geçmişte benzer sinyallerin gerçekleşme oranı (%); 0–1 ya da 0–100 gelebilir."""
    if not a:
        return None
    v = a.get("hit_rate")
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return None
    return round(v * 100) if v <= 1 else round(v)


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
        hr = hit_rate_pct(analysis)
        if hr is not None:
            lines.append(f"Geçmişte benzer sinyallerin %{hr}'i gerçekleşti.")
        if not confidence_is_informative(analysis):
            lines.append(
                "UYARI: Bu varlık/ufuk için güven skoru geçmişte isabeti ayırt etmedi. 'Yüksek güven', 'güçlü sinyal' "
                "deme; yön sinyalinin zayıf, belirsizliğin yüksek olduğunu söyle."
            )
        if ind:
            lines.append("Göstergeler: " + ", ".join(f"{k}={v}" for k, v in ind.items()))
        if analysis.get("weights"):
            lines.append("Model ağırlıkları: " + ", ".join(f"{k}={v}" for k, v in analysis["weights"].items()))
    elif code:
        lines.append("Bu varlık için model verisi şu an alınamadı (veri yok); sayı uydurma.")
    return "\n".join(lines)


# ---- Son N günlük fiyatların istem özeti (grafik okuma için) ---------------------------------------


def _r(v: float) -> float:
    return round(v, 4) if abs(v) < 10 else round(v, 2)


def _swings(closes: list[float], window: int = 5) -> tuple[list[float], list[float]]:
    """Yerel dipler ve tepeler: her iki yanındaki `window` günün en düşüğü/en yükseği olan kapanışlar."""
    lows, highs = [], []
    for i in range(window, len(closes) - window):
        seg = closes[i - window : i + window + 1]
        if closes[i] == min(seg):
            lows.append(closes[i])
        if closes[i] == max(seg):
            highs.append(closes[i])
    return lows, highs


def _cluster(levels: list[float], tol: float = 0.015, keep: int = 4) -> list[float]:
    """Birbirine %1,5'ten yakın seviyeleri tek seviyede birleştirir; en çok test edilenleri döner."""
    groups: list[list[float]] = []
    for v in sorted(levels):
        if groups and abs(v - groups[-1][-1]) / max(abs(groups[-1][-1]), 1e-9) <= tol:
            groups[-1].append(v)
        else:
            groups.append([v])
    groups.sort(key=len, reverse=True)
    return sorted(_r(sum(g) / len(g)) for g in groups[:keep])


def price_summary(prices: list[dict[str, Any]] | None) -> str | None:
    """Son N günün kapanışlarını LLM'in kullanabileceği kısa, sayısal bir özete çevirir.

    Tüm sayılar veriden hesaplanır; model destek/direnç seviyelerini görselden tahmin etmek yerine
    bu adaylarla karşılaştırır (halüsinasyonu azaltır).
    """
    if not prices:
        return None
    rows = [p for p in prices if p.get("close") is not None]
    if len(rows) < 2:
        return None
    closes = [float(p["close"]) for p in rows]
    first, last = closes[0], closes[-1]
    chg = (last - first) / first * 100 if first else 0.0
    d0, d1 = rows[0].get("date"), rows[-1].get("date")
    span = f" ({d0} – {d1})" if d0 and d1 else ""
    lines = [
        f"Son {len(closes)} işlem günü{span}: ilk {_r(first)}, son {_r(last)}, değişim %{chg:.1f}",
        f"En düşük {_r(min(closes))}, en yüksek {_r(max(closes))}",
    ]
    for n in (20, 50):
        if len(closes) >= n:
            lines.append(f"{n} günlük ortalama: {_r(sum(closes[-n:]) / n)}")
    lows, highs = _swings(closes)
    if lows:
        lines.append("Destek adayları (yerel dipler): " + ", ".join(str(v) for v in _cluster(lows)))
    if highs:
        lines.append("Direnç adayları (yerel tepeler): " + ", ".join(str(v) for v in _cluster(highs)))
    lines.append("Son 10 kapanış: " + ", ".join(str(_r(v)) for v in closes[-10:]))
    return "\n".join(lines)
