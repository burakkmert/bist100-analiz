"""Güven kalibrasyonu testleri: sentetik fiyat ve sahte tahminler; internet/DB gerekmez."""
import numpy as np
import pandas as pd

from backtest.confidence_calibration import (calibration_table, load_ohlc_frames, rank_correlation,
                                             replay, score)

HORIZONS = [1, 5, 20]
MODELS = ["timesfm", "chronos", "naive_drift"]


def ohlc(n: int = 520, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.015, n)))
    return pd.DataFrame({"date": pd.bdate_range("2023-01-02", periods=n).date, "open": close,
                         "high": close * 1.01, "low": close * 0.99, "close": close,
                         "adj_close": np.nan, "volume": 1e7})


def make_raw(df: pd.DataFrame, origins: list[int], code: str = "AAA", band: float = 0.08) -> pd.DataFrame:
    close = df["close"].to_numpy()
    rows = []
    for t in origins:
        for h in HORIZONS:
            for m in MODELS:
                rows.append({"model": m, "code": code, "origin_date": df["date"].iloc[t], "horizon": h,
                             "y0": close[t], "y": close[t + h], "p10": close[t] * (1 - band),
                             "p50": close[t], "p90": close[t] * (1 + band), "type": "stock"})
    return pd.DataFrame(rows)


def test_replay_produces_scored_rows_without_future_leak():
    df = ohlc()
    types = {"AAA": "stock"}
    frames = load_ohlc_frames(["AAA"], types, reader=lambda c: df.copy())
    raw = make_raw(df, [300, 350, 400, 450])
    out = replay(raw, frames, types)
    assert len(out) == 4 * 3                                   # 4 gün × 3 ufuk
    assert set(out["direction"]) <= {"up", "down", "flat"}
    assert out["confidence"].between(0, 100).all()
    assert out["hit"].isin([0.0, 1.0]).all()


def test_flat_forecast_is_flat_and_hit_depends_on_realized_move():
    df = ohlc()
    types = {"AAA": "stock"}
    frames = load_ohlc_frames(["AAA"], types, reader=lambda c: df.copy())
    out = replay(make_raw(df, [300, 350, 400, 450]), frames, types)
    assert (out["direction"] == "flat").all()                  # p50 = son fiyat -> değişim 0 -> flat
    expect = (out["move"].abs() <= out["tol"]).astype(float)
    assert (out["hit"] == expect).all()


def test_score_hit_rules():
    d = pd.DataFrame({"direction": ["up", "up", "down", "down", "flat", "flat"],
                      "move": [0.02, -0.01, -0.02, 0.01, 0.001, 0.05],
                      "tol": [0.01] * 6, "confidence": [80] * 6, "type": "stock", "horizon": 5})
    assert score(d)["hit"].tolist() == [1.0, 0.0, 1.0, 0.0, 1.0, 0.0]


def test_calibration_table_buckets_and_base_rate():
    rng = np.random.default_rng(1)
    n = 400
    conf = rng.integers(20, 100, n)
    hit_p = np.where(conf >= 80, 0.8, 0.5)                      # güven yüksekken gerçekten daha isabetli
    d = pd.DataFrame({"type": "stock", "horizon": 5, "direction": "up", "confidence": conf,
                      "hit": (rng.random(n) < hit_p).astype(float),
                      "inside": 0.0, "up_move": (rng.random(n) < 0.5).astype(float)})
    tab = calibration_table(d, min_n=10)
    assert set(tab["bucket"]) <= {"<50", "50-59", "60-69", "70-79", "80-89", "90-100"}
    hi = tab[tab["bucket"].isin(["80-89", "90-100"])]["hit_rate"].mean()
    lo = tab[tab["bucket"].isin(["<50", "50-59"])]["hit_rate"].mean()
    assert hi > lo
    assert rank_correlation(d, min_n=50)["spearman"].iloc[0] > 0


def test_calibration_empty_input():
    assert calibration_table(score(pd.DataFrame())).empty
