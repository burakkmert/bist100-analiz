"""Walk-forward backtest (Görev 6).

Her varlık için son `test_days` işlem günü içinde her `step` günde bir "tahmin günü" (t) seçilir.
Model YALNIZCA t gününe kadarki veriyi görür (seri[:t+1]); tahmin, t+h günündeki gerçek fiyatla
karşılaştırılır. Model hiçbir zaman geleceği görmez.

Verimlilik: tüm (varlık, tahmin günü) bağlamları tek sözlükte toplanıp modele bir kerede verilir;
GPU modelleri bunları batch'ler hâlinde işler. Anahtar: "KOD|t".

Çıktı (uzun tablo), her satır bir (model, varlık, tahmin günü, ufuk):
    model, code, origin_date, horizon, target_date, y0, y, p10, p50, p90
y0 = tahmin günündeki fiyat, y = h gün sonraki gerçek fiyat.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from ml.models.base import Forecaster

RESULT_COLUMNS = ["model", "code", "origin_date", "horizon", "target_date", "y0", "y", "p10", "p50", "p90"]


def origin_indices(n: int, test_days: int, step: int, min_context: int, min_h: int = 1) -> list[int]:
    """Tahmin günlerinin dizinleri: son `test_days` gün içinde, her `step` günde bir.
    En az `min_context` geçmiş ve en az `min_h` gün sonrası olan günler seçilir.
    Son tahmin günü en sondan geriye doğru hizalanır (en yeni veriler değerlendirilir)."""
    last = n - 1 - min_h
    first = max(min_context - 1, n - 1 - test_days)
    if last < first:
        return []
    return list(range(last, first - 1, -step))[::-1]


def build_contexts(frames: dict[str, pd.DataFrame], test_days: int, step: int, min_context: int,
                   context_length: int) -> tuple[dict[str, np.ndarray], list[tuple[str, int]]]:
    """Dönüş: ({"KOD|t": bağlam dizisi}, [(kod, t), ...])."""
    contexts, keys = {}, []
    for code, df in frames.items():
        px = df["price"].to_numpy(dtype="float64")
        for t in origin_indices(len(px), test_days, step, min_context):
            contexts[f"{code}|{t}"] = px[max(0, t + 1 - context_length): t + 1]
            keys.append((code, t))
    return contexts, keys


def evaluate(pred: pd.DataFrame, frames: dict[str, pd.DataFrame], model_name: str) -> pd.DataFrame:
    """Tahminleri gerçekleşen fiyatlarla eşleştirir; ufku veri sonunu aşanlar atılır."""
    if pred.empty:
        return pd.DataFrame(columns=RESULT_COLUMNS)
    parts = pred["code"].str.rsplit("|", n=1, expand=True)
    pred = pred.assign(asset=parts[0], t=parts[1].astype(int))
    rows = []
    for asset, g in pred.groupby("asset", sort=False):
        df = frames[asset]
        px, dates = df["price"].to_numpy(), df["date"].to_numpy()
        target = g["t"].to_numpy() + g["horizon"].to_numpy()
        ok = target < len(px)
        g, target = g[ok], target[ok]
        rows.append(pd.DataFrame({
            "model": model_name, "code": asset,
            "origin_date": dates[g["t"].to_numpy()], "horizon": g["horizon"].to_numpy(),
            "target_date": dates[target], "y0": px[g["t"].to_numpy()], "y": px[target],
            "p10": g["p10"].to_numpy(), "p50": g["p50"].to_numpy(), "p90": g["p90"].to_numpy(),
        }))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=RESULT_COLUMNS)


def run_walk_forward(frames: dict[str, pd.DataFrame], models: list[Forecaster], horizons: list[int],
                     test_days: int = 504, step: int = 5, min_context: int = 120,
                     context_length: int = 512, log=print) -> tuple[pd.DataFrame, list[dict]]:
    contexts, keys = build_contexts(frames, test_days, step, min_context, context_length)
    log(f"Walk-forward: {len(frames)} varlık, {len(contexts)} tahmin günü×varlık bağlamı")
    results, stats = [], []
    models = list(models)
    while models:
        model = models.pop(0)
        t0 = time.time()
        try:
            pred = model.predict(contexts, horizons)
            res = evaluate(pred, frames, model.name)
            status = "ok"
        except Exception as exc:
            res, status = pd.DataFrame(columns=RESULT_COLUMNS), f"failed: {str(exc)[:200]}"
        dur = round(time.time() - t0, 1)
        log(f"[{model.name}] {status}, {len(res)} değerlendirme, {dur} sn")
        stats.append({"model": model.name, "status": status, "rows": int(len(res)), "duration_s": dur})
        results.append(res)
        del model
        try:
            from ml.batch_forecast import free_gpu
            free_gpu()
        except Exception:
            pass
    out = pd.concat(results, ignore_index=True) if results else pd.DataFrame(columns=RESULT_COLUMNS)
    return out, stats
