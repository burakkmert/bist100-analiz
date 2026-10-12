"""Görev 7: bağlam uzunluğu deneylerini tek tabloda karşılaştırır.

Girdi: backtest/reports/ altındaki *_ctx<N>.csv dosyaları (run_backtest --tag ctx<N> çıktıları).
Çıktı: ekrana özet + reports/context_comparison_<tarih>.csv

Kullanım:
    python -m backtest.compare_contexts                 # bugünün dosyaları
    python -m backtest.compare_contexts --date 2026-10-11
"""
from __future__ import annotations

import argparse
import re
from datetime import date

import pandas as pd

from backtest.run_backtest import REPORT_DIR


def load(kind: str, day: str) -> pd.DataFrame:
    frames = []
    for path in sorted(REPORT_DIR.glob(f"{kind}_{day}_ctx*.csv")):
        ctx = int(re.search(r"_ctx(\d+)\.csv$", path.name).group(1))
        frames.append(pd.read_csv(path).assign(context=ctx))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def main(argv=None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--date", default=date.today().isoformat())
    a = p.parse_args(argv)

    dm = load("diebold_mariano", a.date)
    metr = load("by_type_model_horizon", a.date)
    if dm.empty or metr.empty:
        print(f"{REPORT_DIR} içinde {a.date} tarihli _ctx dosyası yok. Önce context_experiment.ps1 çalıştır.")
        return

    pd.set_option("display.width", 200)
    for kind in ("stock", "fund"):
        print(f"\n######## {kind.upper()}")
        for model in ("timesfm", "chronos"):
            d = dm[(dm["type"] == kind) & (dm["model"] == model) & (dm["vs"] == "naive_drift")]
            if d.empty:
                continue
            ratio = d.pivot(index="context", columns="horizon", values="rel_loss").round(3)
            pval = d.pivot(index="context", columns="horizon", values="p_value").round(3)
            print(f"-- {model} / naive_drift hata oranı (< 1 iyi), parantezde p")
            print((ratio.astype(str) + " (" + pval.astype(str) + ")").to_string())
            cov = metr[(metr["type"] == kind) & (metr["model"] == model)]
            print(f"-- {model} kapsama (%80 aralık, ideal 0.80)")
            print(cov.pivot(index="context", columns="horizon", values="coverage").round(3).to_string())

    best = (dm[dm["vs"] == "naive_drift"].sort_values("rel_loss")
            .groupby(["type", "model", "horizon"]).head(1)
            [["type", "model", "horizon", "context", "rel_loss", "p_value"]]
            .sort_values(["type", "model", "horizon"]))
    print("\n######## Her (tür, model, ufuk) için en iyi bağlam")
    print(best.round(3).to_string(index=False))

    out = REPORT_DIR / f"context_comparison_{a.date}.csv"
    dm.merge(metr[["type", "model", "horizon", "context", "mase", "coverage", "dir_acc"]],
             on=["type", "model", "horizon", "context"], how="left").to_csv(out, index=False)
    print(f"\nTablo: {out}")


if __name__ == "__main__":
    main()
