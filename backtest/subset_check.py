"""Veri kalitesi / likidite kesitleri: modeller "temiz" hisse alt kümelerinde basit kıyası geçiyor mu?

Soru: modellerin hissede tutmaması kirli/seyrek işlem gören hisselerden mi kaynaklanıyor?
Kesitler (yalnızca hisse):
  * likit100   : son 250 günde ortalama işlem tutarı (kapanış × hacim) en yüksek 100 hisse
  * likit_disi : geri kalanlar
  * sik_islem  : sıfır getirili gün oranı < %5 (fiyatı her gün değişen hisseler)
  * seyrek     : sıfır getirili gün oranı >= %5
Her kesitte timesfm/chronos vs naive_drift için DM testi (backtest.metrics.dm_table) ve yön doğruluğu.

Kullanım:
    python -m backtest.subset_check --raw backtest/reports/raw_2026-10-12_u500.parquet
Çıktı: ekrana tablo + backtest/summary/kesit_dm.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from backtest.metrics import dm_table

SUMMARY = Path(__file__).resolve().parent / "summary"
TOP_N = 100
ZERO_RET_LIMIT = 0.05
LOOKBACK = 250
MODELS = ["timesfm", "chronos"]
REF = "naive_drift"


def liquidity_stats(df: pd.DataFrame, lookback: int = LOOKBACK) -> dict:
    """Tek hisse için: ortalama işlem tutarı ve sıfır getirili gün oranı (son `lookback` satır)."""
    d = df.sort_values("date").tail(lookback + 1)
    close = pd.to_numeric(d["close"], errors="coerce")
    vol = pd.to_numeric(d["volume"], errors="coerce") if "volume" in d else pd.Series(np.nan, index=d.index)
    ret = close.pct_change().dropna()
    return {"turnover": float((close * vol).mean()),
            "zero_ret": float((ret.abs() < 1e-12).mean()) if len(ret) else np.nan}


def assign_subsets(stats: pd.DataFrame, top_n: int = TOP_N, zero_limit: float = ZERO_RET_LIMIT) -> dict[str, list[str]]:
    """stats: indeks=kod, sütunlar turnover, zero_ret. Dönüş: kesit adı -> kod listesi."""
    s = stats.dropna(subset=["turnover"])
    top = s["turnover"].nlargest(top_n).index
    z = stats["zero_ret"]
    return {"likit100": list(top),
            "likit_disi": [c for c in s.index if c not in set(top)],
            "sik_islem": list(z[z < zero_limit].index),
            "seyrek": list(z[z >= zero_limit].index)}


def subset_dm(raw: pd.DataFrame, subsets: dict[str, list[str]], step: int = 5) -> pd.DataFrame:
    """Her kesit için model / naive_drift kayıp oranı (rel_loss < 1: model daha iyi) ve DM p-değeri."""
    out = []
    for name, codes in subsets.items():
        sub = raw[raw["code"].isin(codes)]
        if sub.empty or REF not in set(sub["model"]):
            continue
        t = dm_table(sub, MODELS, [REF], step=step)
        if t.empty:
            continue
        t.insert(0, "kesit", name)
        t.insert(1, "n_hisse", sub["code"].nunique())
        out.append(t[["kesit", "n_hisse", "horizon", "model", "rel_loss", "rel_loss_median", "p_value"]])
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Likidite / veri kalitesi kesitlerinde model karşılaştırması")
    p.add_argument("--raw", required=True)
    p.add_argument("--step", type=int, default=5)
    a = p.parse_args(argv)

    from data.collectors.bist_prices import read_cache

    raw = pd.read_parquet(a.raw)
    if "type" in raw:
        raw = raw[raw["type"] == "stock"]
    stats = {}
    for code in sorted(raw["code"].unique()):
        df = read_cache(code)
        if df is not None and not df.empty:
            stats[code] = liquidity_stats(df)
    stats = pd.DataFrame(stats).T
    subsets = assign_subsets(stats)
    print({k: len(v) for k, v in subsets.items()})

    res = subset_dm(raw, subsets, a.step)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_rows", 200)
    print("\n== rel_loss < 1 ve p < 0,05 → model basit kıyastan anlamlı iyi")
    print(res.round(4).to_string(index=False))
    SUMMARY.mkdir(exist_ok=True)
    res.round(4).to_csv(SUMMARY / "kesit_dm.csv", index=False)
    print(f"\nKaydedildi: {SUMMARY / 'kesit_dm.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
