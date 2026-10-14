"""Dinamik ağırlıklı ensemble (Görev 5.1).

Her (varlık, ufuk) için:
  ağırlık_m ∝ 1 / MAE_m   (model_errors: son 60 günde o varlıkta o ufuktaki ortalama mutlak hata)
  p_q = Σ ağırlık_m × p_q,m   (q ∈ {10, 50, 90}; kantil ortalaması —
                               Kişi 1'in ml/scenarios.py'siyle aynı yöntem)

Kurallar
- Hata kaydı olmayan modelin ağırlığı, hatası bilinen modellerin ortalama ağırlığı kadardır;
  hiçbir modelin hatası yoksa ağırlıklar eşittir (ilk gün / yeni varlık).
- Hiçbir model min_weight'in altına düşmez (tek modele aşırı güven olmasın), sonra yeniden normalize edilir.
- Bandın sırası korunur: p10 ≤ p50 ≤ p90.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

Quantiles = tuple[float, float | None, float]  # (p10, p50, p90); 120 günde p50 None olabilir


@dataclass(frozen=True)
class Ensemble:
    p10: float
    p50: float
    p90: float
    weights: dict[str, float]  # analysis.weights JSON'una yazılır


def _valid(x: float | None) -> bool:
    return x is not None and math.isfinite(x) and x > 0


def weights(models: list[str], mae: dict[str, float | None], min_weight: float = 0.1) -> dict[str, float]:
    """1/MAE ağırlıkları, alt sınır uygulanmış ve toplamı 1."""
    if not models:
        return {}
    inv = {m: 1 / mae[m] for m in models if _valid(mae.get(m))}
    if not inv:
        raw = {m: 1.0 for m in models}
    else:
        mean_inv = sum(inv.values()) / len(inv)
        raw = {m: inv.get(m, mean_inv) for m in models}
    total = sum(raw.values())
    w = {m: v / total for m, v in raw.items()}

    # Alt sınır: altında kalanları sabitle, kalanı diğerlerine oranla dağıt (birkaç turda yakınsar)
    floor = min(min_weight, 1 / len(models))
    fixed: dict[str, float] = {}
    for _ in range(len(models)):
        low = {m for m, v in w.items() if m not in fixed and v < floor}
        if not low:
            break
        for m in low:
            fixed[m] = floor
        free = {m: raw[m] for m in models if m not in fixed}
        rest = 1 - sum(fixed.values())
        s = sum(free.values())
        w = {**fixed, **{m: rest * v / s for m, v in free.items()}}
    return w


def combine(
    forecasts: dict[str, Quantiles], mae: dict[str, float | None], min_weight: float = 0.1
) -> Ensemble:
    """Model bantlarını tek bantta birleştirir. forecasts: {model: (p10, p50, p90)}.
    p50'si olmayan model (120 gün) p10–p90 orta noktasıyla temsil edilir."""
    usable = {
        m: q
        for m, q in forecasts.items()
        if q[0] is not None and q[2] is not None and math.isfinite(q[0]) and math.isfinite(q[2])
    }
    if not usable:
        raise ValueError("Birleştirilecek geçerli tahmin yok")
    w = weights(sorted(usable), mae, min_weight)
    p10 = sum(w[m] * usable[m][0] for m in usable)
    p90 = sum(w[m] * usable[m][2] for m in usable)
    p50 = sum(
        w[m] * (usable[m][1] if usable[m][1] is not None else (usable[m][0] + usable[m][2]) / 2)
        for m in usable
    )
    lo, mid, hi = sorted((p10, p50, p90))
    return Ensemble(p10=lo, p50=mid, p90=hi, weights={m: round(v, 4) for m, v in w.items()})


def agreement(
    forecasts: dict[str, Quantiles],
    w: dict[str, float],
    last_price: float,
    direction: str,
    threshold: float | None = None,
) -> float:
    """Ensemble yönüyle aynı yönü gösteren modellerin ağırlık payı (0–1).
    flat yönde: `threshold` verilirse p50'si son fiyata eşikten yakın olan modeller 'aynı yönde' sayılır
    (karar motoru böyle çağırır). Verilmezse bandı son fiyatı içerenler — bu çok gevşektir: geniş bantlı
    her model son fiyatı içerir ve uyum hep ~1 çıkar."""
    share = 0.0
    for m, wm in w.items():
        p10, p50, p90 = forecasts[m]
        mid = p50 if p50 is not None else (p10 + p90) / 2
        if direction == "up":
            ok = mid > last_price
        elif direction == "down":
            ok = mid < last_price
        elif threshold is not None:
            ok = abs(mid - last_price) <= threshold
        else:
            ok = p10 <= last_price <= p90
        share += wm if ok else 0
    return min(1.0, share)
