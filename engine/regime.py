"""Piyasa rejimi tespiti (Görev 5.2): trend / range (yatay) / high_vol (yüksek oynaklık).

Öncelik sırası:
  1) high_vol : bugünkü 20 günlük volatilite, son 1 yılın %80'inden yüksek VE yıllık medyanın en az
                1,2 katıysa (oynaklığı hiç değişmeyen sakin seride küçük gürültü "yüksek" sayılmasın)
  2) trend    : hissede ADX(14) > 25; fonda (OHLC yok) Kaufman verimlilik oranı ER(20) > 0.30
  3) range    : diğer durumlar

Aynı fonksiyon BIST100 (XU100) için de çalıştırılır: piyasa geneli rejim, güven skorunda bağlam olarak
kullanılır (karar motoru). Hepsi yalnızca geçmiş veriyle hesaplanır (veri sızıntısı yok).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from engine import indicators as ind

DEFAULTS = {
    "adx_period": 14,
    "adx_trend": 25,
    "er_window": 20,
    "er_trend": 0.30,
    "vol_lookback": 252,
    "high_vol_percentile": 0.80,
    "high_vol_min_ratio": 1.2,
}


@dataclass(frozen=True)
class Regime:
    name: str  # "trend" | "range" | "high_vol"
    details: dict = field(default_factory=dict)  # tez/"neden bu sinyal?" için ölçümler


def adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Ortalama Yön Endeksi (Wilder). high/low düzeltilmiş fiyata ölçeklenir (indicators.atr gibi)."""
    price = ind.price_series(df)
    factor = price / df["close"].astype(float)
    high = df["high"].astype(float) * factor
    low = df["low"].astype(float) * factor
    up = high.diff()
    down = -low.diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)
    atr = ind.atr(df, n)
    plus_di = 100 * ind._wilder(plus_dm, n) / atr
    minus_di = 100 * ind._wilder(minus_dm, n) / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    return ind._wilder(dx, n)


def efficiency_ratio(price: pd.Series, n: int = 20) -> pd.Series:
    """Kaufman ER: |net değişim| / Σ|günlük değişim|. 1 = dümdüz trend, 0 = yerinde sayma."""
    net = (price - price.shift(n)).abs()
    path = price.diff().abs().rolling(n, min_periods=n).sum()
    return (net / path).where(path > 0, 0.0)


def vol_percentile(vol20: pd.Series, lookback: int = 252) -> tuple[float, float] | None:
    """Son değerin son `lookback` gündeki volatilite dağılımındaki yüzdeliği (0–1) ve medyana oranı."""
    hist = vol20.dropna().iloc[-lookback:]
    if len(hist) < 60:  # yeterli geçmiş yoksa karar verme
        return None
    med = float(hist.median())
    ratio = float(hist.iloc[-1] / med) if med > 0 else 1.0
    return float((hist <= hist.iloc[-1]).mean()), ratio


def classify(df: pd.DataFrame, params: dict | None = None, table: pd.DataFrame | None = None) -> Regime:
    """df: tek varlığın fiyat tablosu (tarih sıralı).
    table: önceden hesaplanmış indicators.compute çıktısı (verilmezse hesaplanır)."""
    p = {**DEFAULTS, **(params or {})}
    t = table if table is not None else ind.compute(df)
    details: dict = {}

    vp = vol_percentile(t["vol20"], p["vol_lookback"])
    details["vol20"] = ind._clean(t["vol20"].iloc[-1], 2)
    details["vol_percentile"] = None if vp is None else round(vp[0], 3)
    details["vol_to_median"] = None if vp is None else round(vp[1], 3)
    if vp is not None and vp[0] > p["high_vol_percentile"] and vp[1] >= p["high_vol_min_ratio"]:
        return Regime("high_vol", details)

    if ind.has_ohlc(df):
        a = adx(df, p["adx_period"]).iloc[-1]
        details["adx"] = ind._clean(a, 2)
        trending = bool(np.isfinite(a) and a > p["adx_trend"])
    else:
        er = efficiency_ratio(ind.price_series(df), p["er_window"]).iloc[-1]
        details["efficiency_ratio"] = ind._clean(er, 3)
        trending = bool(np.isfinite(er) and er > p["er_trend"])
    return Regime("trend" if trending else "range", details)
