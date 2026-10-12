"""Fon kategorisine göre backtest kırılımı (tez için).

Soru: modeller hangi fon türünde naive_drift'e yaklaşıyor ya da geçiyor?
Kategori TEFAS listesinden (data/tefas_funds.csv → category) gelir; boşsa fon adından çıkarılır.

Kullanım:
    python -m backtest.by_category --raw backtest/reports/raw_2026-10-11_ctx512.parquet
    python -m backtest.by_category --raw ... --horizons 30 120 --vs naive_drift
Çıktı: ekrana tablolar + backtest/reports/by_category_<raw adı>.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from backtest.metrics import dm_table, summarize_by

ROOT = Path(__file__).resolve().parent.parent
FUNDS_CSV = ROOT / "data" / "tefas_funds.csv"
REPORTS = Path(__file__).resolve().parent / "reports"

# Sıra önemli: ilk eşleşen kazanır ("Serbest Para Piyasası" -> serbest değil para piyasası
# olsun diye para piyasası önce; "Katılım Hisse" -> hisse olsun diye hisse katılımdan önce).
CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("para_piyasasi", ("para piyasası",)),
    ("altin_maden", ("altın", "kıymetli maden", "gümüş")),
    ("hisse", ("hisse senedi", "hisse")),
    ("borclanma", ("borçlanma", "tahvil", "bono", "eurobond", "kira sertifika", "sukuk")),
    ("fon_sepeti", ("fon sepeti",)),
    ("serbest", ("serbest",)),
    ("degisken_karma", ("değişken", "karma", "dengeli")),
    ("katilim", ("katılım",)),
]


def tr_lower(text: str) -> str:
    """Türkçe küçük harf: 'İ'->'i', 'I'->'ı' (str.lower 'İ'yi 'i̇' yapar)."""
    return str(text).replace("İ", "i").replace("I", "ı").lower()


def category_from_name(name: str) -> str:
    low = tr_lower(name)
    for cat, keys in CATEGORY_RULES:
        if any(k in low for k in keys):
            return cat
    return "diger"


def normalize_category(raw_cat, name: str) -> str:
    """TEFAS kategorisi varsa onu kurallardan geçirir, yoksa fon adına bakar."""
    if isinstance(raw_cat, str) and raw_cat.strip():
        cat = category_from_name(raw_cat)
        if cat != "diger":
            return cat
    return category_from_name(name)


def load_fund_categories(path: Path = FUNDS_CSV) -> pd.Series:
    df = pd.read_csv(path, dtype={"code": str})
    raw_cat = df["category"] if "category" in df else pd.Series([None] * len(df))
    cats = [normalize_category(c, n) for c, n in zip(raw_cat, df["name"].fillna(""))]
    return pd.Series(cats, index=df["code"].str.upper(), name="category")


def category_tables(raw: pd.DataFrame, cats: pd.Series, horizons: list[int],
                    models: list[str], vs: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = raw[(raw["type"] == "fund") & raw["horizon"].isin(horizons)].copy() if "type" in raw else \
        raw[raw["horizon"].isin(horizons)].copy()
    d["category"] = d["code"].map(cats).fillna("diger")
    d = d[d["model"].isin(models + [vs, "naive"])]

    summ = summarize_by(d, ["category", "horizon", "model"])
    n_assets = d.groupby("category")["code"].nunique().rename("n_varlik")
    summ = summ.merge(n_assets, on="category")
    dm = dm_table(d, models, [vs], by=["category"])
    return summ, dm


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Fon kategorisine göre backtest kırılımı")
    p.add_argument("--raw", required=True)
    p.add_argument("--funds", default=str(FUNDS_CSV))
    p.add_argument("--horizons", type=int, nargs="+", default=[5, 30, 120])
    p.add_argument("--models", nargs="+", default=["timesfm", "chronos"])
    p.add_argument("--vs", default="naive_drift")
    a = p.parse_args(argv)

    raw = pd.read_parquet(a.raw)
    cats = load_fund_categories(Path(a.funds))
    summ, dm = category_tables(raw, cats, a.horizons, a.models, a.vs)

    pd.set_option("display.width", 200)
    print("== Kategori başına fon sayısı")
    print(summ.drop_duplicates("category").set_index("category")["n_varlik"]
          .sort_values(ascending=False).to_string())

    print(f"\n== MASE (naive'e göre; < 1 = naive'den iyi)")
    print(summ.pivot_table(index=["category", "model"], columns="horizon", values="mase")
          .round(3).to_string())

    print(f"\n== Kapsama (%80 aralık; ideal ≈ 0.80)")
    print(summ.pivot_table(index=["category", "model"], columns="horizon", values="coverage")
          .round(3).to_string())

    print(f"\n== Diebold–Mariano: model / {a.vs} (< 1 ve p < 0.05 -> anlamlı daha iyi)")
    if len(dm):
        dm["hucre"] = dm.apply(lambda r: f"{r.rel_loss:.3f} (p={r.p_value:.3g})", axis=1)
        print(dm.pivot_table(index=["category", "model"], columns="horizon", values="hucre",
                             aggfunc="first").to_string())

    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / f"by_category_{Path(a.raw).stem}.csv"
    summ.merge(dm.drop(columns="hucre", errors="ignore"), how="left",
               on=["category", "horizon", "model"]).to_csv(out, index=False)
    print(f"\nKaydedildi: {out}")


if __name__ == "__main__":
    main()
