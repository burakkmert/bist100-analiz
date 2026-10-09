"""Gece toplu tahmin işi (Görev 5) — 20:00, run_daily'den sonra.

Akış:
  1) Evren: data/bist_stocks.csv + data/tefas_funds.csv (aktif varlıklar)
  2) Her varlığın temiz fiyat serisi önbellekten okunur; min_history'den kısa olanlar atlanır
  3) Her model tüm serileri batch'ler hâlinde tahmin eder; GPU belleği modeller arasında boşaltılır
  4) Çıktı `forecasts` tablosu biçiminde: code, run_date, model, horizon, p10, p50, p90
     - 120 günlük ufukta p50 YAZILMAZ (NULL) — nokta tahmin yok, yalnızca bant
  5) ml/cache/forecasts_<tarih>.csv + isteğe bağlı --db upsert

Hata politikası: bir model toplu tahminde hata verirse o model varlık varlık tekrar denenir;
yalnızca hatalı varlıklar atlanır. Bir model tamamen çökerse diğer modeller devam eder.
Tüm modeller başarısızsa çıkış kodu 1.

Kullanım:
    python -m ml.batch_forecast                              # tüm evren, config'teki tüm modeller
    python -m ml.batch_forecast --models naive timesfm       # yalnızca bazı modeller
    python -m ml.batch_forecast --codes THYAO GARAN IPB      # hızlı deneme
    python -m ml.batch_forecast --limit 50                   # ilk 50 varlık (süre ölçümü)
    python -m ml.batch_forecast --db                         # DATABASE_URL'e de yaz
"""
from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from data.collectors.bist_prices import read_cache
from ml.models.base import Forecaster, load_config
from ml.models.registry import build_models

OUT_DIR = Path(__file__).resolve().parent / "cache"
FORECAST_COLUMNS = ["code", "run_date", "model", "horizon", "p10", "p50", "p90"]
NO_POINT_HORIZONS = {120}  # bu ufuklarda p50 yazılmaz


# ---------------------------------------------------------------- girdi

def load_universe_codes(codes: list[str] | None = None) -> pd.DataFrame:
    """code, type sütunlu evren. codes verilirse yalnızca onlar."""
    from data.collectors.bist_list import load_stock_list
    from data.collectors.tefas_list import FUNDS_CSV, load_fund_list

    stocks = load_stock_list()[["code", "type"]]
    funds = load_fund_list()[["code"]].assign(type="fund") if FUNDS_CSV.exists() else pd.DataFrame(columns=["code", "type"])
    uni = pd.concat([stocks, funds], ignore_index=True).drop_duplicates("code")
    if codes:
        wanted = {c.upper() for c in codes}
        uni = uni[uni["code"].isin(wanted)]
        missing = wanted - set(uni["code"])
        if missing:  # listede olmayan kod da denenebilsin (ör. yeni fon)
            uni = pd.concat([uni, pd.DataFrame({"code": sorted(missing), "type": "unknown"})])
    return uni.reset_index(drop=True)


def load_series(codes: list[str], min_history: int, reader=read_cache,
                types: dict[str, str] | None = None) -> tuple[dict[str, np.ndarray], dict[str, str]]:
    """Dönüş: ({kod: fiyat dizisi}, {kod: atlanma nedeni}).
    İmkânsız sıçramalar (bedelsiz, TEFAS kayıt hatası) okuma anında düzeltilir."""
    from data.cleaning import adjust_jumps, market_calendar

    types = types or {}
    frames, skipped = {}, {}
    for code in codes:
        df = reader(code)
        if df is None or df.empty:
            skipped[code] = "veri yok"
            continue
        df = df[df["close"] > 0].sort_values("date").drop_duplicates("date", keep="last")
        frames[code] = df

    stock_cal = market_calendar([f for c, f in frames.items() if types.get(c) == "stock"])
    series = {}
    for code, df in frames.items():
        kind = "stock" if types.get(code) == "stock" else "fund"
        df = adjust_jumps(df, kind, stock_cal if kind == "stock" else None)
        px = df["adj_close"].fillna(df["close"]) if "adj_close" in df else df["close"]
        px = px.to_numpy(dtype="float64")
        px = px[np.isfinite(px) & (px > 0)]
        if len(px) < min_history:
            skipped[code] = f"kısa geçmiş ({len(px)} < {min_history})"
            continue
        series[code] = px
    return series, skipped


# ---------------------------------------------------------------- tahmin

def predict_resilient(model: Forecaster, series: dict[str, np.ndarray], horizons: list[int]) -> tuple[pd.DataFrame, dict[str, str]]:
    """Önce toplu; hata olursa varlık varlık. Dönüş: (tahminler, {kod: hata})."""
    try:
        return model.predict(series, horizons), {}
    except Exception as exc:
        print(f"  [{model.name}] toplu tahmin hatası ({exc}); varlık varlık deneniyor...")
    parts, errors = [], {}
    for code, s in series.items():
        try:
            parts.append(model.predict({code: s}, horizons))
        except Exception as exc:
            errors[code] = str(exc)[:200]
    out = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    return out, errors


def free_gpu() -> None:
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def to_forecast_rows(df: pd.DataFrame, model_name: str, run_date: date) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=FORECAST_COLUMNS)
    out = df.assign(model=model_name, run_date=run_date)
    out.loc[out["horizon"].isin(NO_POINT_HORIZONS), "p50"] = np.nan
    return out[FORECAST_COLUMNS]


def run(series: dict[str, np.ndarray], models: list[Forecaster], horizons: list[int],
        run_date: date) -> tuple[pd.DataFrame, list[dict]]:
    frames, stats = [], []
    models = list(models)
    while models:  # listeden çıkararak ilerle: biten modelin GPU belleği serbest kalsın
        model = models.pop(0)
        t0 = time.time()
        try:
            out, errors = predict_resilient(model, series, horizons)
            status = "ok" if not errors else "partial"
        except Exception as exc:  # model yüklenemedi vb.
            out, errors, status = pd.DataFrame(), {"*": str(exc)[:200]}, "failed"
        n_ok = out["code"].nunique() if not out.empty else 0
        if n_ok == 0:
            status = "failed"
        dur = round(time.time() - t0, 1)
        print(f"[{model.name}] {status}: {n_ok}/{len(series)} varlık, {dur} sn"
              + (f", {len(errors)} hata" if errors else ""))
        stats.append({"model": model.name, "status": status, "assets_ok": n_ok,
                      "errors": errors, "duration_s": dur})
        frames.append(to_forecast_rows(out, model.name, run_date))
        del model
        free_gpu()
    result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=FORECAST_COLUMNS)
    return result, stats


# ---------------------------------------------------------------- çıktı

def upsert_forecasts_db(df: pd.DataFrame, database_url: str, chunk: int = 5000) -> int:
    from sqlalchemy import MetaData, Table, create_engine
    from sqlalchemy.dialects.postgresql import insert

    engine = create_engine(database_url)
    table = Table("forecasts", MetaData(), autoload_with=engine)
    clean = df[FORECAST_COLUMNS].astype(object)
    records = clean.where(clean.notna(), None).to_dict("records")
    with engine.begin() as conn:
        for i in range(0, len(records), chunk):
            stmt = insert(table).values(records[i:i + chunk])
            conn.execute(stmt.on_conflict_do_update(
                index_elements=["code", "run_date", "model", "horizon"],
                set_={c: stmt.excluded[c] for c in ("p10", "p50", "p90")},
            ))
    return len(records)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Gece toplu tahmin işi (20:00)")
    p.add_argument("--models", nargs="*", help="Boşsa config.yaml'daki tüm modeller")
    p.add_argument("--codes", nargs="*", help="Yalnızca bu varlıklar")
    p.add_argument("--limit", type=int, help="İlk N varlık (süre ölçümü için)")
    p.add_argument("--run-date", help="YYYY-MM-DD (varsayılan: bugün)")
    p.add_argument("--db", action="store_true", help="forecasts tablosuna da yaz")
    args = p.parse_args(argv)

    t0 = time.time()
    cfg = load_config()
    run_date = date.fromisoformat(args.run_date) if args.run_date else date.today()
    universe = load_universe_codes(args.codes)
    codes = universe["code"].tolist()[: args.limit] if args.limit else universe["code"].tolist()

    types = dict(zip(universe["code"], universe["type"]))
    series, skipped = load_series(codes, cfg.get("min_history", 120), types=types)
    print(f"Evren: {len(codes)} varlık | tahmin edilecek: {len(series)} | atlanan: {len(skipped)}")
    if not series:
        print("Tahmin edilecek seri yok. Önce: python -m data.run_daily", file=sys.stderr)
        return 1

    models = build_models(args.models, cfg)
    result, stats = run(series, models, cfg["horizons"], run_date)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = OUT_DIR / f"forecasts_{run_date.isoformat()}.csv"
    result.to_csv(out_csv, index=False)
    report = {
        "run_date": run_date.isoformat(),
        "assets_universe": len(codes),
        "assets_forecast": len(series),
        "skipped": skipped,
        "models": stats,
        "rows": int(len(result)),
        "duration_s": round(time.time() - t0, 1),
    }
    (OUT_DIR / f"forecast_report_{run_date.isoformat()}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    if args.db:
        url = os.environ.get("DATABASE_URL")
        if not url:
            print("--db için DATABASE_URL gerekli", file=sys.stderr)
            return 1
        print(f"DB: {upsert_forecasts_db(result, url)} satır upsert edildi")

    print(f"\nBitti: {len(result)} satır -> {out_csv}")
    print(f"Toplam süre: {report['duration_s']} sn")
    return 0 if any(s["status"] != "failed" for s in stats) else 1


if __name__ == "__main__":
    sys.exit(main())
