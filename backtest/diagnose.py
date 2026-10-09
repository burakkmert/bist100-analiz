"""Backtest teşhis aracı: iki modelin farkını hangi varlıklar / günler yaratıyor?

Kullanım:
    python -m backtest.diagnose --raw backtest/reports/raw_2026-10-10.parquet \
        --type fund --horizon 120 --model timesfm --vs naive_drift
"""
from __future__ import annotations

import argparse

import pandas as pd


def main(argv=None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--raw", required=True)
    p.add_argument("--type", default="fund")
    p.add_argument("--horizon", type=int, default=120)
    p.add_argument("--model", default="timesfm")
    p.add_argument("--vs", default="naive_drift")
    p.add_argument("--top", type=int, default=10)
    a = p.parse_args(argv)

    raw = pd.read_parquet(a.raw)
    d = raw[(raw["horizon"] == a.horizon) & (raw["model"].isin([a.model, a.vs]))]
    if "type" in d:
        d = d[d["type"] == a.type]
    d = d.dropna(subset=["p50", "y", "y0"]).assign(loss=lambda x: (x["y"] - x["p50"]).abs() / x["y0"])
    w = d.pivot_table(index=["code", "origin_date"], columns="model", values="loss").dropna()
    m, r = w[a.model], w[a.vs]
    daily = w.groupby(level="origin_date").mean()

    print(f"{a.type} | h={a.horizon} | {a.model} vs {a.vs} | {len(w)} eşleşmiş gözlem, "
          f"{w.index.get_level_values('code').nunique()} varlık, {len(daily)} gün")
    print(f"  Oran (tüm gözlemler, MASE gibi): {m.mean() / r.mean():.3f}")
    print(f"  Oran (gün ağırlıklı)           : {daily[a.model].mean() / daily[a.vs].mean():.3f}")
    print(f"  Oran (medyan)                  : {m.median() / r.median():.3f}")
    print(f"  {a.model} daha iyi olduğu gözlem oranı: {(m < r).mean():.3f}")

    diff = (m - r).groupby(level="code").sum().sort_values()
    share = diff / (m - r).sum() if (m - r).sum() != 0 else diff * 0
    print(f"\n-- Farkı en çok {a.model} ALEYHİNE büyüten {a.top} varlık (toplam kayıp farkı)")
    print(pd.DataFrame({"fark": diff, "pay": share}).tail(a.top)[::-1].round(3).to_string())
    print(f"\n-- {a.model} LEHİNE en büyük {a.top} varlık")
    print(pd.DataFrame({"fark": diff, "pay": share}).head(a.top).round(3).to_string())

    worst = w.assign(fark=m - r).sort_values("fark").tail(a.top)[::-1]
    print(f"\n-- En kötü {a.top} tekil gözlem ({a.model} kaybı - {a.vs} kaybı)")
    print(worst.round(4).to_string())


if __name__ == "__main__":
    main()
