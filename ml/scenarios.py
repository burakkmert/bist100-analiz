"""30 / 120 gün senaryoları (Görev 8) → `scenarios` tablosu: code, run_date, horizon, bear, base, bull.

30 gün:
    Modellerin p10 / p50 / p90 değerlerinin ağırlıklı ortalaması (kantil ortalaması).
    Ağırlık ∝ 1 / MAE (model_errors, aynı varlık ve ufuk); hata tablosu yoksa eşit ağırlık.
    bear = p10, base = p50, bull = p90.

120 gün — NOKTA TAHMİN YOK, yalnızca bant:
    Backtest'te modellerin 120 günlük bandı fonlarda fazla dardı (kapsama ~0,61–0,69).
    Bant, tarihsel oynaklık bandıyla genişletilir: trendli naive'in p10 / p90'ı (son fiyat ×
    trend, ± günlük oynaklık × √120) ile model bandının daha geniş olan ucu alınır.
        bear = min(model_p10, oynaklık_p10), bull = max(model_p90, oynaklık_p90)
        base = √(bear × bull)  — bandın geometrik ortası; tahmin değil, "orta senaryo" etiketi.

Kullanım:
    python -m ml.scenarios                                   # bugünün forecasts + model_errors dosyaları
    python -m ml.scenarios --db                              # scenarios tablosuna da yaz
    python -m ml.scenarios --evaluate backtest/reports/raw_2026-10-10.parquet   # bant kapsaması (tez)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from ml.models.base import load_config

OUT_DIR = Path(__file__).resolve().parent / "cache"
SCENARIO_COLUMNS = ["code", "run_date", "horizon", "bear", "base", "bull"]
# Düz naive yok: fonlar faiz işlettiği için "fiyat sabit" bandı fonlarda yalnızca %32 kapsıyor ve
# kantil ortalamasını aşağı çekiyordu (backtest değerlendirmesi: fon 30g kapsama 0,55).
DEFAULT_MODELS = ["timesfm", "chronos", "naive_drift"]
MIN_PRICE_FRAC = 1e-4   # negatif/sıfır alt sınır yerine: üst sınırın binde biri (fiyat negatif olamaz)
WIDEN_WITH = "naive_drift"


def model_weights(errors: pd.DataFrame | None, models: list[str]) -> pd.DataFrame:
    """(code, horizon, model) -> ağırlık. Ağırlık ∝ 1/mae, her (code, horizon) içinde toplam 1."""
    if errors is None or errors.empty:
        return pd.DataFrame(columns=["code", "horizon", "model", "w"])
    e = errors[errors["model"].isin(models) & (errors["mae"] > 0)].copy()
    e["w"] = 1.0 / e["mae"]
    e["w"] = e["w"] / e.groupby(["code", "horizon"])["w"].transform("sum")
    return e[["code", "horizon", "model", "w"]]


def combine(forecasts: pd.DataFrame, weights: pd.DataFrame, models: list[str]) -> pd.DataFrame:
    """Modellerin kantillerini ağırlıklı ortalar. Ağırlığı olmayan (code, horizon) için eşit ağırlık.
    Dönüş: code, run_date, horizon, p10, p50, p90."""
    f = forecasts[forecasts["model"].isin(models)].copy()
    f = f.merge(weights, on=["code", "horizon", "model"], how="left")
    missing = f["w"].isna()
    if missing.any():   # eşit ağırlık
        f.loc[missing, "w"] = 1.0 / f[missing].groupby(["code", "horizon"])["model"].transform("count")
    f["w"] = f["w"] / f.groupby(["code", "run_date", "horizon"])["w"].transform("sum")
    out = []
    for q in ("p10", "p50", "p90"):
        part = f.dropna(subset=[q])
        wq = part["w"] / part.groupby(["code", "run_date", "horizon"])["w"].transform("sum")
        out.append((part[q] * wq).groupby([part["code"], part["run_date"], part["horizon"]]).sum().rename(q))
    return pd.concat(out, axis=1).reset_index()


def build_scenarios(forecasts: pd.DataFrame, errors: pd.DataFrame | None = None,
                    models: list[str] | None = None, widen_with: str = WIDEN_WITH) -> pd.DataFrame:
    models = models or DEFAULT_MODELS
    f = forecasts[forecasts["horizon"].isin([30, 120])].copy()
    f[["p10", "p50", "p90"]] = f[["p10", "p50", "p90"]].apply(pd.to_numeric, errors="coerce")
    ens = combine(f, model_weights(errors, models), models)

    s30 = ens[ens["horizon"] == 30].rename(columns={"p10": "bear", "p50": "base", "p90": "bull"})

    s120 = ens[ens["horizon"] == 120][["code", "run_date", "horizon", "p10", "p90"]]
    ref = f[(f["model"] == widen_with) & (f["horizon"] == 120)][["code", "run_date", "p10", "p90"]]
    s120 = s120.merge(ref, on=["code", "run_date"], how="left", suffixes=("", "_vol"))
    for c in ("p10", "p90", "p10_vol", "p90_vol"):
        s120[c] = pd.to_numeric(s120[c], errors="coerce")
    s120["bear"] = np.fmin(s120["p10"], s120["p10_vol"])
    s120["bull"] = np.fmax(s120["p90"], s120["p90_vol"])
    floor = s120["bull"] * MIN_PRICE_FRAC
    s120["bear"] = np.fmax(s120["bear"], floor)          # negatif alt sınır olmaz
    s120["base"] = np.sqrt(s120["bear"] * s120["bull"])

    s30 = s30.assign(bear=np.fmax(s30["bear"], s30["bull"] * MIN_PRICE_FRAC))
    out = pd.concat([s30[SCENARIO_COLUMNS], s120[SCENARIO_COLUMNS]], ignore_index=True)
    q = np.sort(out[["bear", "base", "bull"]].to_numpy(dtype="float64"), axis=1)   # bear <= base <= bull
    out[["bear", "base", "bull"]] = q
    return out.dropna(subset=["bear", "bull"]).sort_values(["code", "horizon"]).reset_index(drop=True)


# ---------------------------------------------------------------- değerlendirme (tez)

def evaluate_on_backtest(raw: pd.DataFrame, models: list[str] | None = None) -> pd.DataFrame:
    """Backtest ham sonuçları üzerinde senaryo bandının kapsaması ve genişliği.
    Her tahmin günü ayrı bir 'run_date' gibi işlenir; ağırlıklar eşit (geleceği görmemek için)."""
    models = models or DEFAULT_MODELS
    r = raw[raw["horizon"].isin([30, 120]) & raw["model"].isin(set(models) | {WIDEN_WITH, "naive"})]
    fc = r.rename(columns={"origin_date": "run_date"})[["code", "run_date", "model", "horizon", "p10", "p50", "p90"]]
    sc = build_scenarios(fc[fc["model"].isin(set(models) | {WIDEN_WITH})], None, models)
    truth = r[["code", "origin_date", "horizon", "y", "y0"]].drop_duplicates(["code", "origin_date", "horizon"])
    sc = sc.merge(truth.rename(columns={"origin_date": "run_date"}), on=["code", "run_date", "horizon"])
    if "type" in raw:
        sc["type"] = sc["code"].map(raw.drop_duplicates("code").set_index("code")["type"])
    else:
        sc["type"] = "all"
    sc["inside"] = (sc["y"] >= sc["bear"]) & (sc["y"] <= sc["bull"])
    sc["width_pct"] = (sc["bull"] - sc["bear"]) / sc["y0"] * 100
    rows = [{"type": t, "horizon": h, "model": "senaryo", "coverage": g["inside"].mean(),
             "width_pct": g["width_pct"].mean(), "n": len(g)} for (t, h), g in sc.groupby(["type", "horizon"])]
    # kıyas: tek tek modellerin kendi bandı (naive de gösterilir, senaryoda kullanılmasa da)
    for m in sorted(set(models) | {"naive"}):
        mm = r[r["model"] == m].copy()
        mm["type"] = mm["type"] if "type" in mm else "all"
        for (t, h), g in mm.groupby(["type", "horizon"]):
            rows.append({"type": t, "horizon": h, "model": m,
                         "coverage": ((g["y"] >= g["p10"]) & (g["y"] <= g["p90"])).mean(),
                         "width_pct": ((g["p90"] - g["p10"]) / g["y0"] * 100).mean(), "n": len(g)})
    return pd.DataFrame(rows).sort_values(["type", "horizon", "model"]).reset_index(drop=True)


# ---------------------------------------------------------------- giriş noktası

def upsert_scenarios_db(df: pd.DataFrame, database_url: str) -> int:
    from sqlalchemy import MetaData, Table, create_engine
    from sqlalchemy.dialects.postgresql import insert

    engine = create_engine(database_url)
    table = Table("scenarios", MetaData(), autoload_with=engine)
    records = df[SCENARIO_COLUMNS].astype(object).where(df[SCENARIO_COLUMNS].notna(), None).to_dict("records")
    with engine.begin() as conn:
        stmt = insert(table).values(records)
        conn.execute(stmt.on_conflict_do_update(
            index_elements=["code", "run_date", "horizon"],
            set_={c: stmt.excluded[c] for c in ("bear", "base", "bull")},
        ))
    return len(records)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="30/120 gün senaryoları")
    p.add_argument("--forecasts", help="forecasts CSV (varsayılan: ml/cache/forecasts_<bugün>.csv)")
    p.add_argument("--errors", help="model_errors CSV (varsayılan: ml/cache/model_errors_<bugün>.csv, yoksa eşit ağırlık)")
    p.add_argument("--evaluate", help="Backtest raw parquet: bant kapsamasını ölç (senaryo üretmez)")
    p.add_argument("--db", action="store_true", help="scenarios tablosuna da yaz")
    args = p.parse_args(argv)

    cfg = load_config()
    models = cfg.get("scenarios", {}).get("models", DEFAULT_MODELS)
    pd.set_option("display.width", 200)

    if args.evaluate:
        t = evaluate_on_backtest(pd.read_parquet(args.evaluate), models)
        print("== Senaryo bandı vs tek modeller (kapsama ideal ≈ 0.80, genişlik % son fiyata göre)")
        print(t.round(3).to_string(index=False))
        return 0

    today = date.today().isoformat()
    fpath = Path(args.forecasts) if args.forecasts else OUT_DIR / f"forecasts_{today}.csv"
    if not fpath.exists():
        print(f"{fpath} yok. Önce: python -m ml.batch_forecast", file=sys.stderr)
        return 1
    forecasts = pd.read_csv(fpath)
    epath = Path(args.errors) if args.errors else OUT_DIR / f"model_errors_{today}.csv"
    errors = pd.read_csv(epath) if epath.exists() else None
    print(f"Tahminler: {fpath.name} | ağırlıklar: {epath.name if errors is not None else 'eşit (model_errors yok)'}")

    sc = build_scenarios(forecasts, errors, models)
    out = OUT_DIR / f"scenarios_{today}.csv"
    sc.to_csv(out, index=False)
    if args.db:
        url = os.environ.get("DATABASE_URL")
        if not url:
            print("--db için DATABASE_URL gerekli", file=sys.stderr)
            return 1
        print(f"DB: {upsert_scenarios_db(sc, url)} satır upsert edildi")

    for code in [c for c in ("THYAO", "GARAN", "IPB", "TTE") if c in set(sc["code"])]:
        g = sc[sc["code"] == code]
        print(f"  {code}: " + " | ".join(f"{int(r.horizon)}g {r.bear:.2f} / {r.base:.2f} / {r.bull:.2f}"
                                         for r in g.itertuples()))
    print(f"\nBitti: {sc['code'].nunique()} varlık, {len(sc)} satır -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
