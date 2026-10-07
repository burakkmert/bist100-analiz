"""Fiyat temizleme (Görev 3).

Kurallar:
- Sıfır/negatif kapanış      → satır silinir, sorun olarak raporlanır.
- Aynı gün iki kayıt         → son kayıt kalır.
- Tek günlük ±%40 üstü sıçrama → SİLİNMEZ, işaretlenir. (Bedelsiz/bölünme sonrası
  düzeltilmemiş veri olabilir ya da gerçek bir hareket; karar insanın.)
- Eksik iş günü               → piyasa takvimine göre (tüm varlıkların işlem gördüğü
  günlerin birleşimi) eksik günler raporlanır; doldurulmaz.

Hisselerde sıçrama `adj_close` üzerinden ölçülür (bölünme etkisi zaten düzeltilmiş).
"""
from __future__ import annotations

import pandas as pd

MAX_DAILY_JUMP = 0.40
ISSUE_COLUMNS = ["code", "date", "issue", "value"]


def price_series(df: pd.DataFrame) -> pd.Series:
    """Analizde kullanılacak fiyat: adj_close varsa o, yoksa close."""
    adj = df["adj_close"] if "adj_close" in df else None
    return adj.fillna(df["close"]) if adj is not None else df["close"]


def clean_prices(df: pd.DataFrame, max_jump: float = MAX_DAILY_JUMP) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Tek varlığın fiyat tablosunu temizler. Dönüş: (temiz tablo, sorunlar tablosu)."""
    issues = []
    if df.empty:
        return df, pd.DataFrame(columns=ISSUE_COLUMNS)

    df = df.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)

    bad = df["close"].isna() | (df["close"] <= 0)
    for _, r in df[bad].iterrows():
        issues.append({"code": r["code"], "date": r["date"], "issue": "nonpositive_price", "value": r["close"]})
    df = df[~bad].reset_index(drop=True)

    ret = price_series(df).pct_change()
    for i in ret.index[ret.abs() > max_jump]:
        issues.append({"code": df.at[i, "code"], "date": df.at[i, "date"],
                       "issue": "jump", "value": round(float(ret[i]), 4)})

    return df, pd.DataFrame(issues, columns=ISSUE_COLUMNS)


def market_calendar(frames: list[pd.DataFrame], min_share: float = 0.5) -> list:
    """Piyasa takvimi: varlıkların en az yarısının işlem gördüğü günler.
    (Tek bir hissenin hatalı günü takvime girmesin diye eşik kullanılır.)"""
    frames = [f for f in frames if not f.empty]
    if not frames:
        return []
    counts = pd.concat([f[["date"]] for f in frames]).value_counts("date")
    return sorted(counts[counts >= max(1, len(frames) * min_share)].index)


def missing_days(df: pd.DataFrame, calendar: list) -> list:
    """Varlığın ilk ve son günü arasında, takvimde olup varlıkta olmayan günler."""
    if df.empty or not calendar:
        return []
    first, last = min(df["date"]), max(df["date"])
    have = set(df["date"])
    return [d for d in calendar if first <= d <= last and d not in have]
