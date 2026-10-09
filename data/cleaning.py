"""Fiyat temizleme (Görev 3).

Kurallar:
- Sıfır/negatif kapanış      → satır silinir, sorun olarak raporlanır.
- Aynı gün iki kayıt         → son kayıt kalır.
- İmkânsız günlük sıçrama    → işaretlenir; `adjust_jumps` ile okuma anında düzeltilir.
    Hisse: |getiri| > 1,10^k - 1 + %2, k = iki kayıt arasında geçen piyasa seansı sayısı
           (BIST günlük fiyat marjı ±%10). 1 seans: %12, 2 seans: %23 ... Eksik veri günü
           gerçek bir çok günlük hareketi "imkânsız" göstermez. Seans sayısı piyasa takviminden
           (diğer hisselerin işlem günleri) alınır; takvim yoksa iş günü sayılır.
    Fon:   |getiri| > %40 (TEFAS kayıt hatası veya birim fiyat yeniden ayarı)
- Eksik iş günü               → piyasa takvimine göre (tüm varlıkların işlem gördüğü
  günlerin birleşimi) eksik günler raporlanır; doldurulmaz.

Hisselerde sıçrama `adj_close` üzerinden ölçülür (bölünme etkisi zaten düzeltilmiş).
"""
from __future__ import annotations

import pandas as pd

MAX_DAILY_JUMP = 0.40          # fonlar ve uzun boşluklar için
STOCK_DAILY_LIMIT = 0.10       # BIST günlük fiyat marjı
STOCK_MARGIN = 0.02            # yuvarlama / fiyat adımı payı
ISSUE_COLUMNS = ["code", "date", "issue", "value"]


def price_series(df: pd.DataFrame) -> pd.Series:
    """Analizde kullanılacak fiyat: adj_close varsa o, yoksa close."""
    adj = df["adj_close"] if "adj_close" in df else None
    return adj.fillna(df["close"]) if adj is not None else df["close"]


def sessions_between(dates, calendar: list | None = None):
    """Ardışık kayıtlar arasında geçen seans sayısı (ilk satır 1).
    Takvim verilirse (önceki, şimdiki] aralığındaki takvim günleri sayılır; yoksa iş günleri."""
    import numpy as np

    d = pd.to_datetime(pd.Series(list(dates))).dt.date.to_numpy()
    if len(d) < 2:
        return np.ones(len(d), dtype=int)
    if calendar:
        cal = np.array(sorted(pd.to_datetime(pd.Series(list(calendar))).dt.date), dtype="datetime64[D]")
        dd = d.astype("datetime64[D]")
        pos = np.searchsorted(cal, dd, side="right")   # <= tarih olan takvim günü sayısı
        k = np.diff(pos)
    else:
        dd = d.astype("datetime64[D]")
        k = np.busday_count(dd[:-1], dd[1:])
    return np.concatenate([[1], np.maximum(k, 1)])


def implausible_jumps(df: pd.DataFrame, asset_type: str = "fund", calendar: list | None = None) -> pd.Series:
    """Her satır için: önceki kayda göre getiri imkânsız büyüklükte mi? (ilk satır False)
    df tarih sıralı ve temiz olmalı."""
    ret = price_series(df).pct_change()
    if asset_type == "stock":
        k = sessions_between(df["date"], calendar)
        limit = pd.Series((1 + STOCK_DAILY_LIMIT) ** k - 1 + STOCK_MARGIN, index=df.index)
    else:
        limit = MAX_DAILY_JUMP
    return (ret.abs() > limit).fillna(False)


def adjust_jumps(df: pd.DataFrame, asset_type: str = "fund", calendar: list | None = None) -> pd.DataFrame:
    """İmkânsız sıçramaları düzeltir: o günün getirisi 0 sayılır, öncesindeki tüm fiyatlar
    sıçrama oranıyla ölçeklenir. Bedelsiz/bölünmede bu tam olarak geriye dönük düzeltmedir;
    gidip gelen hatalı kayıtlarda iki ölçek birbirini götürür.

    Yalnızca `adj_close` değişir (close ham kalır). Önbelleğe YAZILMAZ: her okumada yeniden
    hesaplanır, böylece yeniden çekilen ham günlerle sahte sıçrama oluşmaz."""
    import numpy as np

    if df.empty or len(df) < 2:
        return df
    df = df.sort_values("date").reset_index(drop=True)
    jumps = implausible_jumps(df, asset_type, calendar).to_numpy()
    if not jumps.any():
        return df
    px = price_series(df).to_numpy(dtype="float64")
    log_r = np.zeros(len(px))
    log_r[jumps] = np.log(px[jumps] / px[np.flatnonzero(jumps) - 1])
    # j gününden SONRAKİ tüm sıçramaların toplam oranı
    after = np.concatenate([np.cumsum(log_r[::-1])[::-1][1:], [0.0]])
    out = df.copy()
    out["adj_close"] = px * np.exp(after)
    return out


def clean_prices(df: pd.DataFrame, max_jump: float | None = None, asset_type: str = "fund",
                 calendar: list | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
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
    flags = (ret.abs() > max_jump).fillna(False) if max_jump is not None else implausible_jumps(df, asset_type, calendar)
    for i in ret.index[flags]:
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
