"""model_errors testleri — sahte veriyle, internet/GPU/DB gerekmez.

Çalıştırma: pytest ml/tests -q
"""
from datetime import date

import numpy as np
import pandas as pd

from ml.model_errors import ERROR_COLUMNS, build_eval_contexts, run
from ml.models.baselines import NaiveDriftForecaster, NaiveForecaster

HORIZONS = [1, 5, 20]


def frame(n=400, drift=0.0, seed=0):
    rng = np.random.default_rng(seed)
    px = 100 * np.exp(np.cumsum(rng.normal(drift, 0.01, n)))
    return pd.DataFrame({"date": pd.bdate_range("2024-01-01", periods=n).date, "price": px})


def test_contexts_cover_window_for_every_horizon():
    ctx = build_eval_contexts({"X": frame(400)}, HORIZONS, window=60, step=5, context_length=512, min_context=120)
    ts = sorted(int(k.split("|")[1]) for k in ctx)
    assert max(ts) == 400 - 1 - 1                       # en yeni: 1 günlük ufuk için dün
    assert min(ts) >= 400 - 20 - 60                     # en eski: en uzun ufuk + pencere
    assert all(b - a == 5 for a, b in zip(ts, ts[1:]))  # düzenli ızgara
    assert all(len(v) <= 512 for v in ctx.values())


def test_errors_only_from_targets_inside_window_and_schema():
    frames = {"A": frame(seed=1), "B": frame(seed=2)}
    out, stats = run(frames, [NaiveForecaster()], HORIZONS, window=60, step=5, as_of=date(2026, 10, 11),
                     log=lambda *a: None)
    assert list(out.columns) == ERROR_COLUMNS + ["n"]
    assert set(out["code"]) == {"A", "B"} and set(out["horizon"]) == set(HORIZONS)
    assert (out["window_days"] == 60).all() and (out["as_of"] == date(2026, 10, 11)).all()
    assert out["dir_acc"].isna().all()                  # naive yön tahmini yapmaz
    assert (out["n"] >= 10).all() and (out["n"] <= 13).all()   # 60 gün / 5 adım ≈ 12
    assert stats[0]["status"] == "ok"


def test_drift_beats_naive_on_trending_fund():
    frames = {"PPF": frame(drift=0.002, seed=3)}       # para piyasası fonu gibi sürekli yükselen
    out, _ = run(frames, [NaiveForecaster(), NaiveDriftForecaster()], HORIZONS, window=60, step=5,
                 log=lambda *a: None)
    m = out.set_index(["model", "horizon"])["mae"]
    assert m[("naive_drift", 20)] < m[("naive", 20)]  # ağırlık trend modeline kaymalı


def test_rows_with_too_few_observations_are_dropped():
    short = frame(130, seed=5)                          # 120 gün eşiğinin hemen üstü: çok az tahmin günü
    out, _ = run({"YENI": short, "ESKI": frame(seed=6)}, [NaiveForecaster()], HORIZONS, window=60, step=5,
                 log=lambda *a: None, min_obs=5)
    assert (out["n"] >= 5).all()
    assert "ESKI" in set(out["code"])
