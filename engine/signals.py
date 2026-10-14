"""Sinyal motoru kuralları (Görev 7) — saf hesap; veritabanı işi run_signals.py'de.

Bu modül "al/sat" demez. Ürettiği şey bir MODEL SİNYALİDİR: arayüzde "alım yönlü model sinyali" /
"satış yönlü model sinyali" olarak gösterilir ve her ekranda yatırım tavsiyesi olmadığı yazar (SPK).

ALIM YÖNLÜ SİNYAL — her kullanıcı için ayrı:
  aday varlıklar = izleme listesi + izlenmeyenlerden en güçlü `universe_top_n` tanesi
                   (izlenmeyen varlıkta eşik `universe_extra_confidence` puan daha yüksek)
  koşullar: yön = up, güven ≥ profil eşiği (temkinli 75 / dengeli 65 / atak 55),
            risk profilin kabul ettikleri arasında, açık pozisyon yok, bekleme süresi dolmuş
  ufuk: 1/5/20 içinde koşulları sağlayan en yüksek güvenli olan (varlık başına bir sinyal)
  kalibrasyon: Kişi 1'in eşlemesi varsa yalnızca güvenin isabeti ayırt ettiği (tür, ufuk, yön)
            anahtarlarında model sinyali üretilir (engine/calibration.py)
  adet: bütçe × profil oranı (%5 / %10 / %15) ÷ fiyat, aşağı yuvarlanmış tam sayı
  zarar-durdur: fiyat − 2 × ATR

SATIŞ YÖNLÜ SİNYAL — kullanıcının açık pozisyonları için:
  (a) model: yön = down ve güven ≥ profil eşiği
  (b) zarar-durdur: son fiyat < zarar-durdur seviyesi (pozisyonun sinyalindeki, yoksa alış − 2 × ATR)
  (c) hedef: son fiyat > analizin üst bandı (p90)
  bekleme süresi burada da geçerli; adet = pozisyonun tamamı

SONUÇ (outcome) — ufuk dolunca:
  realized = sinyal gününden `horizon` işlem günü sonraki kapanış
  hit = alımda realized > giriş, satımda realized < giriş
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

PROFILES = ("cautious", "balanced", "aggressive")


@dataclass(frozen=True)
class AssetView:
    """Bir varlığın o geceki durumu (analysis + son fiyat)."""

    code: str
    price: float
    atr_pct: float | None
    by_horizon: dict[int, dict]  # {ufuk: analysis satırı (direction, confidence, risk, high, ...)}
    asset_type: str = "stock"
    # Güven kalibrasyonunda ayırt edici gücü olan (ufuk, yön) çiftleri; None = kısıtlama yok.
    # Model kaynaklı sinyal yalnızca bunlarda üretilir (zarar-durdur/hedef satışları etkilenmez).
    informative: frozenset[tuple[int, str]] | None = None


@dataclass(frozen=True)
class UserView:
    user_id: Any
    risk_profile: str
    budget: float | None
    watchlist: frozenset[str]
    open_positions: list[dict] = field(default_factory=list)  # {id, code, qty, buy_price, stop_level}
    recent: frozenset[tuple[str, str]] = frozenset()  # bekleme süresindeki (kod, yön) çiftleri


@dataclass(frozen=True)
class SignalDraft:
    user_id: Any
    code: str
    side: str  # "buy" | "sell"
    horizon: int
    confidence: int
    suggested_qty: float | None
    stop_level: float | None
    reason: str  # "model" | "stop" | "target" — yalnızca bildirim metni ve günlük için


def _profile(p: str | None) -> str:
    return p if p in PROFILES else "balanced"


def atr_abs(view: AssetView) -> float | None:
    if view.atr_pct is None or not math.isfinite(view.atr_pct):
        return None
    return view.atr_pct / 100 * view.price


def stop_level(price: float, atr: float | None, multiple: float) -> float | None:
    if atr is None:
        return None
    return round(max(price - multiple * atr, 0.0), 6) or None


def suggested_qty(budget: float | None, fraction: float, price: float) -> float | None:
    if not budget or budget <= 0 or price <= 0:
        return None
    qty = math.floor(budget * fraction / price)
    return float(qty) if qty > 0 else None


def best_horizon(
    view: AssetView, direction: str, min_conf: int, allowed_risk: set[str] | None
) -> dict | None:
    """Koşulları sağlayan ufuklar arasında en yüksek güvenli analiz satırı."""
    ok = [
        a
        for a in view.by_horizon.values()
        if a.get("direction") == direction
        and (view.informative is None or (int(a["horizon"]), direction) in view.informative)
        and (a.get("confidence") or 0) >= min_conf
        and (allowed_risk is None or a.get("risk") in allowed_risk)
    ]
    if not ok:
        return None
    return max(ok, key=lambda a: (a["confidence"], -a["horizon"]))


def buy_signals(user: UserView, assets: dict[str, AssetView], cfg: dict) -> list[SignalDraft]:
    sc = cfg["signals"]
    prof = _profile(user.risk_profile)
    threshold = sc["min_confidence"][prof]
    allowed = set(sc["allowed_risk"][prof])
    holding = {p["code"] for p in user.open_positions}

    def eligible(code: str, min_conf: int) -> tuple[AssetView, dict] | None:
        v = assets.get(code)
        if v is None or code in holding or (code, "buy") in user.recent:
            return None
        a = best_horizon(v, "up", min_conf, allowed)
        return (v, a) if a else None

    picks = [p for c in sorted(user.watchlist) if (p := eligible(c, threshold))]
    extra = [
        p
        for c in sorted(assets)
        if c not in user.watchlist
        if (p := eligible(c, threshold + sc["universe_extra_confidence"]))
    ]
    extra.sort(key=lambda p: -p[1]["confidence"])
    picks += extra[: sc["universe_top_n"]]

    out = []
    for v, a in picks:
        out.append(
            SignalDraft(
                user_id=user.user_id,
                code=v.code,
                side="buy",
                horizon=int(a["horizon"]),
                confidence=int(a["confidence"]),
                suggested_qty=suggested_qty(user.budget, sc["budget_fraction"][prof], v.price),
                stop_level=stop_level(v.price, atr_abs(v), sc["stop_atr_multiple"]),
                reason="model",
            )
        )
    return out


def sell_signals(user: UserView, assets: dict[str, AssetView], cfg: dict) -> list[SignalDraft]:
    sc = cfg["signals"]
    threshold = sc["min_confidence"][_profile(user.risk_profile)]
    out, seen = [], set()
    for pos in user.open_positions:
        code = pos["code"]
        v = assets.get(code)
        if v is None or code in seen or (code, "sell") in user.recent:
            continue
        atr = atr_abs(v)
        stop = pos.get("stop_level") or stop_level(float(pos["buy_price"]), atr, sc["stop_atr_multiple"])
        model = best_horizon(v, "down", threshold, None)
        a5 = v.by_horizon.get(5) or next(iter(v.by_horizon.values()), None)

        reason, ref = None, None
        if stop is not None and v.price < stop:
            reason, ref = "stop", model or a5
        elif model is not None:
            reason, ref = "model", model
        elif a5 is not None and a5.get("high") is not None and v.price > float(a5["high"]):
            reason, ref = "target", a5
        if reason is None or ref is None:
            continue
        seen.add(code)
        out.append(
            SignalDraft(
                user_id=user.user_id,
                code=code,
                side="sell",
                horizon=int(ref["horizon"]),
                confidence=int(ref.get("confidence") or 0),
                suggested_qty=float(pos["qty"]),
                stop_level=stop,
                reason=reason,
            )
        )
    return out


def signals_for_user(user: UserView, assets: dict[str, AssetView], cfg: dict) -> list[SignalDraft]:
    return sell_signals(user, assets, cfg) + buy_signals(user, assets, cfg)


def cooldown_since(today: date, cfg: dict) -> date:
    return today - timedelta(days=cfg["signals"]["cooldown_days"])


def evaluate_outcome(
    side: str, entry: float, closes_after: list[tuple[date, float]], horizon: int
) -> dict | None:
    """closes_after: sinyal gününden SONRAKİ işlem günlerinin (tarih, kapanış) listesi, eskiden yeniye.
    Ufuk dolmadıysa None (sinyal açık kalır)."""
    if len(closes_after) < horizon or entry <= 0:
        return None
    d, realized = closes_after[horizon - 1]
    ret = (realized / entry - 1) * 100
    hit = realized > entry if side == "buy" else realized < entry
    return {
        "entry": round(entry, 6),
        "realized": round(realized, 6),
        "return_pct": round(ret, 4),
        "hit": bool(hit),
        "evaluated_on": d.isoformat(),
    }
