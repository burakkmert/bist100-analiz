"""Gece model hata tablosu (Görev 6) → `model_errors`. Kişi 2'nin ensemble ağırlıkları buna dayanır.

Her (varlık, model, ufuk) için: hedef günü son `window_days` işlem günü içine düşen tahminlerin
hatası. Tahminler walk-forward ile yeniden üretilir — model hiçbir zaman tahmin gününden sonrasını
görmez. Böylece geçmiş tahmin arşivi olmadan da ilk günden çalışır.

Sütunlar (shared/db_schema.sql):
    code, model, horizon, window_days, mae, mape, dir_acc, as_of
    mae  : TL cinsinden ort |gerçek - p50|  (varlık içi karşılaştırma için; ağırlık ∝ 1/mae)
    mape : yüzde
    dir_acc : yön doğruluğu (naive için tanımsız -> NULL)
Ek sütunlar (CSV'de, DB'ye yazılmaz): n (değerlendirilen tahmin sayısı)

Kullanım:
    python -m ml.model_errors                          # tüm evren, config'teki modeller
    python -m ml.model_errors --codes THYAO IPB --models naive naive_drift timesfm
    python -m ml.model_errors --db                     # model_errors tablosuna yaz
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from backtest.metrics import direction_hits
from backtest.walk_forward import evaluate
from ml.batch_forecast import free_gpu, load_price_frames, load_universe_codes
from ml.models.base import Forecaster, load_config
from ml.models.registry import build_models

OUT_DIR = Path(__file__).resolve().parent / "cache"
ERROR_COLUMNS = ["code", "model", "horizon", "window_days", "mae", "mape", "dir_acc", "as_of"]


def build_eval_contexts(frames: dict[str, pd.DataFrame], horizons: list[int], window: int, step: int,
                        context_length: int, min_context: int) -> dict[str, np.ndarray]:
    """Hedefi son `window` güne düşebilecek tahmin günleri için bağlamlar: {"KOD|t": dizi}.
    Tek, düzenli bir ızgara (dünden geriye `step` aralıkla, en uzun ufuk + pencere kadar);
    her ufuk bu ızgaradan hedefi pencereye düşenleri kullanır (errors_from_eval süzer)."""
    contexts = {}
    max_h = max(horizons)
    for code, df in frames.items():
        px = df["price"].to_numpy(dtype="float64")
        n = len(px)
        first = max(min_context - 1, n - max_h - window)
        for t in range(n - 2, first - 1, -step):
            contexts[f"{code}|{t}"] = px[max(0, t + 1 - context_length): t + 1]
    return contexts


def errors_from_eval(res: pd.DataFrame, frames: dict[str, pd.DataFrame], window: int,
                     as_of: date) -> pd.DataFrame:
    """Hedef günü son `window` içinde olanları süzer, (varlık, model, ufuk) bazında hata hesaplar."""
    if res.empty:
        return pd.DataFrame(columns=ERROR_COLUMNS + ["n"])
    cutoff = {c: df["date"].iloc[max(0, len(df) - window)] for c, df in frames.items()}
    res = res[res["target_date"] >= res["code"].map(cutoff)].dropna(subset=["p50", "y", "y0"])
    rows = []
    for (code, model, h), g in res.groupby(["code", "model", "horizon"]):
        err = (g["y"] - g["p50"]).abs()
        hits, n_dir = direction_hits(g["y"], g["p50"], g["y0"])
        rows.append({
            "code": code, "model": model, "horizon": int(h), "window_days": window,
            "mae": float(err.mean()),
            "mape": float((err / g["y"].abs()).mean() * 100),
            "dir_acc": hits / n_dir if n_dir else np.nan,
            "as_of": as_of, "n": int(len(g)),
        })
    return pd.DataFrame(rows, columns=ERROR_COLUMNS + ["n"])


def run(frames: dict[str, pd.DataFrame], models: list[Forecaster], horizons: list[int], window: int = 60,
        step: int = 5, context_length: int = 512, min_context: int = 120, as_of: date | None = None,
        log=print) -> tuple[pd.DataFrame, list[dict]]:
    as_of = as_of or date.today()
    contexts = build_eval_contexts(frames, horizons, window, step, context_length, min_context)
    log(f"model_errors: {len(frames)} varlık, {len(contexts)} bağlam, pencere {window} gün")
    parts, stats = [], []
    models = list(models)
    while models:
        model = models.pop(0)
        t0 = time.time()
        try:
            res = evaluate(model.predict(contexts, horizons), frames, model.name)
            out = errors_from_eval(res, frames, window, as_of)
            status = "ok"
        except Exception as exc:
            out, status = pd.DataFrame(columns=ERROR_COLUMNS + ["n"]), f"failed: {str(exc)[:200]}"
        dur = round(time.time() - t0, 1)
        log(f"[{model.name}] {status}, {len(out)} satır, {dur} sn")
        stats.append({"model": model.name, "status": status, "rows": int(len(out)), "duration_s": dur})
        parts.append(out)
        del model
        free_gpu()
    result = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=ERROR_COLUMNS + ["n"])
    return result, stats


def upsert_model_errors_db(df: pd.DataFrame, database_url: str, chunk: int = 5000) -> int:
    from sqlalchemy import MetaData, Table, create_engine
    from sqlalchemy.dialects.postgresql import insert

    engine = create_engine(database_url)
    table = Table("model_errors", MetaData(), autoload_with=engine)
    clean = df[ERROR_COLUMNS].astype(object)
    records = clean.where(clean.notna(), None).to_dict("records")
    with engine.begin() as conn:
        for i in range(0, len(records), chunk):
            stmt = insert(table).values(records[i:i + chunk])
            conn.execute(stmt.on_conflict_do_update(
                index_elements=["code", "model", "horizon", "window_days", "as_of"],
                set_={c: stmt.excluded[c] for c in ("mae", "mape", "dir_acc")},
            ))
    return len(records)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Gece model hata tablosu (model_errors)")
    p.add_argument("--models", nargs="*", help="Boşsa config'teki tüm modeller (ARIMA hariç önerilir)")
    p.add_argument("--codes", nargs="*")
    p.add_argument("--window", type=int, help="Kaç günlük hata penceresi (varsayılan config: 60)")
    p.add_argument("--step", type=int, help="Kaç günde bir tahmin günü (varsayılan config: 5)")
    p.add_argument("--db", action="store_true", help="model_errors tablosuna da yaz")
    args = p.parse_args(argv)

    t0 = time.time()
    cfg = load_config()
    me_cfg = cfg.get("model_errors", {})
    window = args.window or me_cfg.get("window_days", 60)
    step = args.step or me_cfg.get("step", 5)
    names = args.models or me_cfg.get("models")
    universe = load_universe_codes(args.codes)
    types = dict(zip(universe["code"], universe["type"]))
    frames, skipped = load_price_frames(universe["code"].tolist(), cfg.get("min_history", 120), types=types)
    if not frames:
        print("Veri yok. Önce: python -m data.run_daily", file=sys.stderr)
        return 1

    result, stats = run(frames, build_models(names, cfg), cfg["horizons"], window, step,
                        cfg["context_length"], cfg.get("min_history", 120))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = OUT_DIR / f"model_errors_{date.today().isoformat()}.csv"
    result.to_csv(out_csv, index=False)

    if args.db:
        url = os.environ.get("DATABASE_URL")
        if not url:
            print("--db için DATABASE_URL gerekli", file=sys.stderr)
            return 1
        print(f"DB: {upsert_model_errors_db(result, url)} satır upsert edildi")

    if not result.empty:
        pd.set_option("display.width", 200)
        summary = result.assign(type=result["code"].map(types)).groupby(["type", "model", "horizon"])["mape"].median()
        print("\n== Medyan MAPE (%), son", window, "gün")
        print(summary.unstack("horizon").round(2).to_string())
    print(f"\nBitti: {len(result)} satır -> {out_csv}  |  {round(time.time() - t0, 1)} sn")
    return 0 if any(s["status"] == "ok" for s in stats) else 1


if __name__ == "__main__":
    sys.exit(main())
