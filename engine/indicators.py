"""Teknik göstergeler (Kişi 2 — karar motoru, Görev 3).

Girdi: tek bir varlığın günlük fiyat tablosu (prices tablosundaki sütunlar), tarihe göre sıralı.
Çıktı: aynı indeksli gösterge tablosu + karar motorunun analysis.indicators alanına yazdığı özet.

Kurallar
- Fiyat olarak adj_close (yoksa close) kullanılır; Kişi 1'in data/cleaning.py'siyle aynı ilke.
  OHLC göstergelerinde high/low da aynı düzeltme oranıyla ölçeklenir (bölünme günü sahte ATR olmasın).
- Fonlarda yalnızca kapanış vardır: ATR yerine kapanış volatilitesi kullanılır; MACD ve hacim atlanır.
- VERİ SIZINTISI YOK: her değer yalnızca o güne kadarki veriyle hesaplanır (yalnızca geriye bakan
  rolling/ewm). tests/test_indicators.py bunu kesme testiyle denetler.
- Yeterli geçmiş yoksa değer NaN (tabloda) / None (özette) olur; uydurma değer üretilmez.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

CONFIG_PATH = Path(__file__).with_name("config.yaml")
TRADING_DAYS = 252

DEFAULTS = {
    "rsi_period": 14,
    "macd": {"fast": 12, "slow": 26, "signal": 9},
    "ma_short": 20,
    "ma_long": 50,
    "atr_period": 14,
    "vol_window": 20,
}


def load_params(path: Path = CONFIG_PATH) -> dict:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    return {**DEFAULTS, **(cfg or {}).get("indicators", {})}


# --------------------------------------------------------------------------- tekil göstergeler


def price_series(df: pd.DataFrame) -> pd.Series:
    """Analiz fiyatı: adj_close varsa o, yoksa close."""
    if "adj_close" in df:
        return df["adj_close"].fillna(df["close"]).astype(float)
    return df["close"].astype(float)


def _wilder(s: pd.Series, n: int) -> pd.Series:
    """Wilder yumuşatması (RSI ve ATR'nin klasik tanımı): alpha = 1/n."""
    return s.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def rsi(price: pd.Series, n: int = 14) -> pd.Series:
    delta = price.diff()
    gain = _wilder(delta.clip(lower=0), n)
    loss = _wilder(-delta.clip(upper=0), n)
    rs = gain / loss
    out = 100 - 100 / (1 + rs)
    # Hiç düşüş yoksa RSI 100, hiç hareket yoksa 50
    out = out.where(loss != 0, np.where(gain > 0, 100.0, 50.0))
    return out.where(gain.notna())


def macd(price: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    ema_fast = price.ewm(span=fast, adjust=False, min_periods=fast).mean()
    ema_slow = price.ewm(span=slow, adjust=False, min_periods=slow).mean()
    line = ema_fast - ema_slow
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame({"macd": line, "macd_signal": sig, "macd_hist": line - sig})


def sma(price: pd.Series, n: int) -> pd.Series:
    return price.rolling(n, min_periods=n).mean()


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Ortalama Gerçek Aralık; high/low düzeltilmiş fiyata ölçeklenir."""
    price = price_series(df)
    factor = price / df["close"].astype(float)
    high = df["high"].astype(float) * factor
    low = df["low"].astype(float) * factor
    prev = price.shift(1)
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1, skipna=False)
    return _wilder(tr, n)


def volatility(price: pd.Series, n: int = 20) -> pd.Series:
    """Yıllıklandırılmış kapanış volatilitesi (%), log getirilerden."""
    ret = np.log(price).diff()
    return ret.rolling(n, min_periods=n).std() * math.sqrt(TRADING_DAYS) * 100


def has_ohlc(df: pd.DataFrame) -> bool:
    """Fonlarda (ve eksik hisse verisinde) OHLC yoktur."""
    cols = {"high", "low", "volume"}
    return cols <= set(df.columns) and df[["high", "low"]].notna().any().all()


# --------------------------------------------------------------------------- tablo ve özet


def compute(df: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
    """Tüm göstergeler, df ile aynı indeksle. df tarihe göre artan sıralı olmalı."""
    p = {**DEFAULTS, **(params or {})}
    price = price_series(df)
    out = pd.DataFrame(index=df.index)
    out["price"] = price
    out["rsi"] = rsi(price, p["rsi_period"])
    out["ma20"] = sma(price, p["ma_short"])
    out["ma50"] = sma(price, p["ma_long"])
    # 1.0 = MA20 MA50'nin üstünde, 0.0 = altında, NaN = yeterli geçmiş yok
    above = (out["ma20"] > out["ma50"]).astype(float).where(out["ma50"].notna())
    out["ma20_above_ma50"] = above
    # Kesişim: +1 = bugün yukarı kesti (altın kesişim), -1 = aşağı kesti, 0 = yok
    out["ma_cross"] = above.diff()
    out["vol20"] = volatility(price, p["vol_window"])

    if has_ohlc(df):
        m = p["macd"]
        out = out.join(macd(price, m["fast"], m["slow"], m["signal"]))
        out["atr"] = atr(df, p["atr_period"])
        out["atr_pct"] = out["atr"] / price * 100
        vol = df["volume"].astype(float)
        out["volume_change"] = vol / vol.rolling(p["vol_window"], min_periods=p["vol_window"]).mean() - 1
    else:
        # Fon: ATR'nin yerini günlük kapanış oynaklığı (%) alır; MACD ve hacim yok
        out["atr_pct"] = out["vol20"] / math.sqrt(TRADING_DAYS)
    return out


def _clean(v: Any, digits: int = 4) -> Any:
    """JSON'a uygun değer: NaN/inf → None, numpy → Python, ondalıklar yuvarlanır."""
    if v is None:
        return None
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return round(f, digits)


SNAPSHOT_KEYS = (
    "rsi",
    "macd",
    "macd_signal",
    "macd_hist",
    "ma20",
    "ma50",
    "ma20_above_ma50",
    "ma_cross",
    "atr_pct",
    "vol20",
    "volume_change",
)


def snapshot(table: pd.DataFrame, at: Any = None) -> dict:
    """Bir günün göstergeleri (varsayılan son gün) → analysis.indicators JSON'u.
    Fonlarda olmayan göstergeler anahtar olarak hiç yazılmaz."""
    row = table.iloc[-1] if at is None else table.loc[at]
    out: dict[str, Any] = {}
    for k in SNAPSHOT_KEYS:
        if k not in table.columns:
            continue
        v = row[k]
        if k == "ma20_above_ma50":
            out[k] = None if pd.isna(v) else bool(v)
        elif k == "ma_cross":
            out[k] = None if pd.isna(v) else int(v)
        else:
            out[k] = _clean(v, 2 if k in ("rsi", "atr_pct", "vol20") else 4)
    return out
