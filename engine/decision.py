"""Karar motoru çekirdeği (Görev 5.3–5.5): yön, güven skoru (0–100), risk seviyesi → analysis satırı.

Girdi (tek varlık, tek gece): fiyat geçmişi + ufuk başına model tahminleri + model hataları.
Çıktı: shared/db_schema.sql 'analysis' tablosunun bir satırı (sözlük). Veritabanına yazmayı
run_engine.py yapar; bu modül saf hesaptır, test edilebilir.

Yön
  değişim = ensemble p50 − son fiyat;  eşik = atr_fraction × ATR × √ufuk
  |değişim| > eşik → up/down, değilse flat.  (ATR günlük; ufuk büyüdükçe beklenen oynama √ufuk ile büyür.)

Güven skoru = temel + sinyal gücü + model uyumu − cezalar  (0–100'e kırpılır)
  sinyal gücü : |p50 − fiyat| / ((p90 − p10)/2)  → bandın yarı genişliğine göre ne kadar net (0..1)
  model uyumu : ensemble yönünü gösteren modellerin ağırlık payı (0..1)
  flat        : yön yok demektir; sinyal gücü puanı verilmez, uyum = p50'si eşik içinde kalan modellerin
                payı ve skor `flat_max` ile sınırlanır. (Eskiden flat'te güç ve uyum kendiliğinden ~1 çıkıyor,
                yön bilgisi olmayan satırlar 90+ güven alıyordu.)
  cezalar     : göstergeler yönle çelişiyor (RSI aşırı bölge, MA20/MA50 ters), düşük likidite,
                kısa geçmiş, yüksek oynaklık rejimi
Her bileşen analysis.indicators.confidence_parts'a yazılır ("neden bu sinyal?" ekranı, Aşama 2).

Risk: varlığın KENDİ yıllık volatilitesi (vol20), varlık türüne göre eşiklerle (hisse/fon/endeks ayrı).
  high_vol rejimi (varlığın bugünkü oynaklığı kendi son 1 yılına göre yüksek) riski bir kademe artırır.

Bu modül hiçbir yerde "al/sat" demez; yalnızca model görüşünü sayısallaştırır (SPK kuralı).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from engine import calibration as cal
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


RISK_LEVELS = ("low", "medium", "high")


def risk_level(vol20: float | None, regime: str, cfg: dict, asset_type: str = "stock") -> str:
    """cfg: config.yaml 'risk' bölümü. Türe özel eşik yoksa hisse eşikleri kullanılır."""
    th = cfg.get(asset_type) or cfg.get("stock") or cfg
    if vol20 is None or not math.isfinite(vol20):
        level = 1  # bilinmiyorsa temkinli orta
    elif vol20 < th["low_below"]:
        level = 0
    elif vol20 < th["medium_below"]:
        level = 1
    else:
        level = 2
    if regime == "high_vol":
        level += int(cfg.get("high_vol_bump", 1))
    return RISK_LEVELS[min(level, 2)]


def analyze(
    code: str,
    run_date: Any,
    prices: pd.DataFrame,
    forecasts: dict[int, dict[str, ens.Quantiles]],
    errors: dict[int, dict[str, float | None]],
    cfg: dict | None = None,
    asset_type: str = "stock",
    calibration: dict | None = None,
) -> list[dict]:
    """Bir varlığın tüm kısa ufukları için analysis satırları.

    calibration : Kişi 1'in güven eşlemesi (engine.calibration.load()). Verilirse flat tavanı eşlemeden
                  alınır ve her satıra geçmiş isabet ifadesi (indicators.calibration) eklenir.
                  Backtest yeniden oynatması ham puanı ölçtüğü için bunu VERMEZ.

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
        flat = direction == "flat"
        strength = 0.0 if flat else _clip(abs(change) / half_band)
        agree = ens.agreement(fc, e.weights, last, direction, threshold if flat else None)

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
        cap = cc.get("flat_max", 100) if flat else 100
        if flat and calibration is not None:
            cap = cal.flat_cap(calibration, asset_type, h, cap)
        confidence = int(round(_clip(raw, 0, cap)))

        calib = cal.describe(calibration, asset_type, h, direction, confidence)
        indicators = {
            **snap,
            **({"calibration": calib} if calib is not None else {}),
            "regime_details": regime.details,
            "confidence_parts": {
                "base": cc["base"],
                "strength": round(cc["strength_points"] * strength, 2),
                "agreement": round(cc["agreement_points"] * agree, 2),
                "penalties": penalties,
                "conflicts": conflicts,
                "threshold": round(threshold, 4),
                "change": round(change, 4),
                "cap": cap,
            },
        }
        rows.append(
            {
                "code": code,
                "run_date": run_date,
                "horizon": h,
                "direction": direction,
                "confidence": confidence,
                "risk": risk_level(snap.get("vol20"), regime.name, cfg["risk"], asset_type),
                "regime": regime.name,
                "weights": e.weights,
                "indicators": indicators,
                "low": round(e.p10, 6),
                "mid": round(e.p50, 6),
                "high": round(e.p90, 6),
            }
        )
    return rows
