"""Karar motoru çekirdeği (Görev 5.3–5.5): yön, güven skoru (0–100), risk seviyesi → analysis satırı.

Girdi (tek varlık, tek gece): fiyat geçmişi + ufuk başına model tahminleri + model hataları.
Çıktı: shared/db_schema.sql 'analysis' tablosunun bir satırı (sözlük). Veritabanına yazmayı
run_engine.py yapar; bu modül saf hesaptır, test edilebilir.

Yön
  değişim = ensemble p50 − son fiyat;  eşik = atr_fraction × ATR × √ufuk
  |değişim| > eşik → up/down, değilse flat.  (ATR günlük; ufuk büyüdükçe beklenen oynama √ufuk ile büyür.)

Güven skoru = temel + sinyal gücü + model uyumu − cezalar  (0–100'e kırpılır)
  sinyal gücü : |p50 − fiyat| / ((p90 − p10)/2)  → bandın yarı genişliğine göre ne kadar net (0..1)
                flat'te tersi: değişim eşikten ne kadar küçükse o kadar net
  model uyumu : ensemble yönünü gösteren modellerin ağırlık payı (0..1)
  cezalar     : göstergeler yönle çelişiyor (RSI aşırı bölge, MA20/MA50 ters), düşük likidite,
                kısa geçmiş, yüksek oynaklık rejimi
Her bileşen analysis.indicators.confidence_parts'a yazılır ("neden bu sinyal?" ekranı, Aşama 2).

Risk: yıllık volatilite eşikleri; high_vol rejimi her zaman "high".

Bu modül hiçbir yerde "al/sat" demez; yalnızca model görüşünü sayısallaştırır (SPK kuralı).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from engine import ensemble as ens
from engine import indicators as ind
from engine import regime as reg

CONFIG_PATH = Path(__file__).with_name("config.yaml")


def load_config(path: Path = CONFIG_PATH) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def direction_of(change: float, threshold: float) -> str:
    if change > threshold:
        return "up"
    if change < -threshold:
        return "down"
    return "flat"


def indicator_conflicts(direction: str, snap: dict) -> list[str]:
    """Göstergelerin model yönüyle çeliştiği durumlar (ceza gerekçeleri)."""
    if direction == "flat":
        return []
    out = []
    rsi = snap.get("rsi")
    above = snap.get("ma20_above_ma50")
    hist = snap.get("macd_hist")
    if direction == "up":
        if rsi is not None and rsi >= 70:
            out.append("rsi_asiri_alim")
        if above is False and (hist is None or hist < 0):
            out.append("ortalamalar_dusus_yonlu")
    else:
        if rsi is not None and rsi <= 30:
            out.append("rsi_asiri_satim")
        if above is True and (hist is None or hist > 0):
            out.append("ortalamalar_yukselis_yonlu")
    return out


def turnover_tl(df: pd.DataFrame, window: int = 20) -> float | None:
    """Son `window` günün ortalama TL işlem hacmi (kapanış × adet). Fonda/hacimsiz veride None."""
    if "volume" not in df or df["volume"].isna().all():
        return None
    tl = (df["close"].astype(float) * df["volume"].astype(float)).tail(window)
    return float(tl.mean()) if tl.notna().any() else None


def risk_level(vol20: float | None, regime: str, cfg: dict) -> str:
    if regime == "high_vol":
        return "high"
    if vol20 is None or not math.isfinite(vol20):
        return "medium"  # bilinmiyorsa temkinli orta
    if vol20 < cfg["low_below"]:
        return "low"
    if vol20 < cfg["medium_below"]:
        return "medium"
    return "high"


def analyze(
    code: str,
    run_date: Any,
    prices: pd.DataFrame,
    forecasts: dict[int, dict[str, ens.Quantiles]],
    errors: dict[int, dict[str, float | None]],
    cfg: dict | None = None,
    asset_type: str = "stock",
) -> list[dict]:
    """Bir varlığın tüm kısa ufukları için analysis satırları.

    prices    : tarih sıralı fiyat tablosu (prices tablosu sütunları), son satır = run_date'e kadar
    forecasts : {ufuk: {model: (p10, p50, p90)}} — yalnızca ensemble'a giren modeller
    errors    : {ufuk: {model: mae}}
    """
    cfg = cfg or load_config()
    table = ind.compute(prices, cfg.get("indicators"))
    snap = ind.snapshot(table)
    regime = reg.classify(prices, cfg.get("regime"), table)

    last = float(table["price"].iloc[-1])
    atr_pct = snap.get("atr_pct")
    atr_abs = (atr_pct or 0) / 100 * last
    cc = cfg["confidence"]
    history_days = int(table["price"].notna().sum())
    liquidity = turnover_tl(prices) if asset_type == "stock" else None

    rows = []
    for h in cfg["signals"]["horizons"]:
        fc = forecasts.get(h)
        if not fc:
            continue
        e = ens.combine(fc, errors.get(h, {}), cfg["ensemble"]["min_weight"])
        change = e.p50 - last
        threshold = cfg["direction"]["atr_fraction"] * atr_abs * math.sqrt(h)
        direction = direction_of(change, threshold)

        half_band = max((e.p90 - e.p10) / 2, 1e-12)
        if direction == "flat":
            strength = 1 - _clip(abs(change) / threshold) if threshold > 0 else 0.5
        else:
            strength = _clip(abs(change) / half_band)
        agree = ens.agreement(fc, e.weights, last, direction)

        conflicts = indicator_conflicts(direction, snap)
        penalties = {
            "indicator": cc["penalty_indicator"] * min(len(conflicts), 2),
            "low_liquidity": cc["penalty_low_liquidity"]
            if liquidity is not None and liquidity < cc["min_turnover_tl"]
            else 0,
            "short_history": cc["penalty_short_history"] if history_days < cc["min_history"] else 0,
            "high_vol": cc["penalty_high_vol"] if regime.name == "high_vol" else 0,
        }
        raw = (
            cc["base"]
            + cc["strength_points"] * strength
            + cc["agreement_points"] * agree
            - sum(penalties.values())
        )
        confidence = int(round(_clip(raw, 0, 100)))

        indicators = {
            **snap,
            "regime_details": regime.details,
            "confidence_parts": {
                "base": cc["base"],
                "strength": round(cc["strength_points"] * strength, 2),
                "agreement": round(cc["agreement_points"] * agree, 2),
                "penalties": penalties,
                "conflicts": conflicts,
                "threshold": round(threshold, 4),
                "change": round(change, 4),
            },
        }
        rows.append(
            {
                "code": code,
                "run_date": run_date,
                "horizon": h,
                "direction": direction,
                "confidence": confidence,
                "risk": risk_level(snap.get("vol20"), regime.name, cfg["risk"]),
                "regime": regime.name,
                "weights": e.weights,
                "indicators": indicators,
                "low": round(e.p10, 6),
                "mid": round(e.p50, 6),
                "high": round(e.p90, 6),
            }
        )
    return rows
