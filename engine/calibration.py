"""Güven kalibrasyonu (Kişi 1'in backtest eşlemesi → karar motoru).

Ham güven puanı (0–100) bir olasılık DEĞİLDİR. Kişi 1'in backtest'i (backtest/confidence_mapping.py)
(tür, ufuk, yön) başına "bu puan kovasındaki sinyaller geçmişte yüzde kaç tuttu" eşlemesini çıkarır ve
backtest/summary/confidence_mapping.json'a yazar. Bu modül o dosyayı okur:

  * describe() → kullanıcıya gösterilecek geçmiş isabet ifadesi (analysis.indicators.calibration)
      informative=False ise isabet oranı GÖSTERİLMEZ: "bu türde sinyalin geçmiş isabeti rastgeleden
      ayırt edilemiyor" denir (hisselerde şu an durum bu).
  * flat_cap()  → flat kararında güven tavanı (eşlemenin önerdiği; yoksa config'teki flat_max)
  * informative() → sinyal motoru, ayırt edici gücü olmayan anahtarda bildirim üretmez

Dosya yoksa (henüz üretilmediyse) her şey eskisi gibi çalışır: kalibrasyon bilgisi boş kalır.
Dil: tavsiye değil, geçmiş istatistiği ("Geçmişte benzer model sinyallerinde isabet oranı %X").
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PATH = REPO_DIR / "backtest" / "summary" / "confidence_mapping.json"

# backtest/confidence_calibration.py ile aynı kovalar: [0,50) [50,60) ... [90,101)
BUCKET_EDGES = [0, 50, 60, 70, 80, 90, 101]
BUCKET_LABELS = ["<50", "50-59", "60-69", "70-79", "80-89", "90-100"]


def bucket_of(score: float) -> str:
    for lo, hi, lab in zip(BUCKET_EDGES, BUCKET_EDGES[1:], BUCKET_LABELS, strict=False):
        if lo <= score < hi:
            return lab
    return BUCKET_LABELS[0] if score < 0 else BUCKET_LABELS[-1]


def key_of(asset_type: str, horizon: int, direction: str) -> str:
    return f"{asset_type}|{int(horizon)}|{direction}"


@lru_cache(maxsize=4)
def _load(path: str) -> dict | None:
    p = Path(path)
    if not p.is_file():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) and "keys" in data else None


def load(path: str | Path | None = None) -> dict | None:
    """Eşleme sözlüğü ya da None (dosya yok)."""
    return _load(str(Path(path) if path else DEFAULT_PATH))


def _entry(mapping: dict | None, asset_type: str, horizon: int, direction: str) -> dict | None:
    if not mapping:
        return None
    return mapping.get("keys", {}).get(key_of(asset_type, horizon, direction))


def rate_for(fitted: dict[str, float], bucket: str) -> float:
    """Kovanın eşlenen oranı; kovada yeterli örnek yoksa en yakın kovanınki."""
    if bucket in fitted:
        return float(fitted[bucket])
    order = {lab: i for i, lab in enumerate(BUCKET_LABELS)}
    nearest = min(fitted, key=lambda b: abs(order.get(b, 0) - order[bucket]))
    return float(fitted[nearest])


def describe(
    mapping: dict | None, asset_type: str, horizon: int, direction: str, score: float
) -> dict | None:
    """analysis.indicators.calibration alanı. Eşleme yoksa None."""
    if mapping is None:
        return None
    m = _entry(mapping, asset_type, horizon, direction)
    if m is None or not m.get("fitted"):
        return {"shown": False, "reason": "yetersiz geçmiş veri"}
    if not m.get("informative"):
        return {
            "shown": False,
            "reason": "ayırt edici güç yok",
            "message": (
                "Bu varlık türünde model sinyalinin geçmiş isabeti rastgele isabetten ayırt edilemiyor."
            ),
            "base_rate": m.get("base_rate"),
        }
    rate = rate_for(m["fitted"], bucket_of(score))
    base = m.get("base_rate")
    # Türkçe ek sayıya göre değiştiği için ("%90'ı", "%75'i") ek gerektirmeyen kalıp
    msg = f"Geçmişte benzer model sinyallerinde isabet oranı %{round(rate * 100)}"
    if base is not None:
        msg += f" (kıyas: %{round(base * 100)})"
    return {"shown": True, "hit_rate": round(rate, 4), "base_rate": base, "message": msg + "."}


def flat_cap(mapping: dict | None, asset_type: str, horizon: int, default: int) -> int:
    """flat kararında güven tavanı: eşlemenin önerdiği ile config'teki varsayılanın küçüğü."""
    m = _entry(mapping, asset_type, horizon, "flat")
    cap = m.get("suggested_cap") if m else None
    return min(int(cap), default) if cap is not None else default


def informative(mapping: dict | None, asset_type: str, horizon: int, direction: str) -> bool:
    """Eşleme yoksa True (kısıtlama yok); varsa yalnızca ayırt edici gücü olan anahtarlar."""
    if mapping is None:
        return True
    m = _entry(mapping, asset_type, horizon, direction)
    return bool(m and m.get("informative"))
