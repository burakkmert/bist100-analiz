"""Metrik testleri — elle hesaplanabilen küçük örneklerle.

Çalıştırma: pytest backtest/tests -q
"""
import math

import numpy as np
import pandas as pd
import pytest

from backtest.metrics import (
    binom_pvalue, coverage, direction_accuracy, direction_hits, interval_width_pct,
    mae, mape, mase, summarize, summarize_by,
)


def test_mae_mape():
    assert mae([100, 200], [110, 190]) == 10
    assert mape([100, 200], [110, 190]) == pytest.approx((10 / 100 + 10 / 200) / 2 * 100)


def test_mase_naive_is_one_and_perfect_is_zero():
    y, y0 = [105, 95, 110], [100, 100, 100]
    assert mase(y, y0, y0) == pytest.approx(1.0)   # naive kendisine göre 1
    assert mase(y, y, y0) == 0.0                    # mükemmel tahmin
    assert mase(y, [104, 96, 108], y0) < 1          # naive'den iyi


def test_direction_ignores_flat():
    y0 = [100, 100, 100, 100]
    y = [110, 90, 105, 100]          # son gerçekleşme yatay -> sayılmaz
    f = [101, 101, 100, 99]          # 3. tahmin yatay -> sayılmaz
    assert direction_hits(y, f, y0) == (1, 2)
    assert direction_accuracy(y, f, y0) == 0.5


def test_binom_pvalue():
    assert binom_pvalue(50, 100) == pytest.approx(1.0)
    assert binom_pvalue(65, 100) < 0.01            # %65 isabet 100 denemede anlamlı
    assert math.isnan(binom_pvalue(0, 0))


def test_coverage_and_width():
    assert coverage([5, 15, 25], [0, 10, 30], [10, 20, 40]) == pytest.approx(2 / 3)
    assert interval_width_pct([90], [110], [100]) == pytest.approx(20)


def test_summarize_by_model_horizon():
    rng = np.random.default_rng(0)
    n = 400
    y0 = np.full(n, 100.0)
    y = y0 * np.exp(rng.normal(0, 0.05, n))
    rows = []
    for model, f in [("naive", y0), ("oracle", y)]:
        rows.append(pd.DataFrame({"model": model, "horizon": 5, "y": y, "y0": y0, "p50": f,
                                  "p10": f * 0.94, "p90": f * 1.06}))
    table = summarize_by(pd.concat(rows), ["model", "horizon"]).set_index("model")
    assert table.loc["naive", "mase"] == pytest.approx(1.0)
    assert table.loc["oracle", "mase"] == 0.0
    assert table.loc["oracle", "dir_acc"] == 1.0 and table.loc["oracle", "dir_pvalue"] < 1e-6
    assert 0.7 < table.loc["naive", "coverage"] < 0.85   # ±%6 bant, σ=%5 -> ~%77
    assert table.loc["oracle", "coverage"] == 1.0


def test_summarize_handles_missing_p50_for_120():
    df = pd.DataFrame({"y": [110, 90], "y0": [100, 100], "p50": [np.nan, np.nan],
                       "p10": [80, 80], "p90": [120, 120]})
    s = summarize(df)
    assert s["n"] == 0 and math.isnan(s["mae"])   # nokta metriği yok
    assert s["coverage"] == 1.0                   # bant metriği var


def test_float32_rounding_is_flat_not_direction():
    y0 = np.array([287.5, 100.0])
    f = y0.astype("float32").astype("float64") * (1 - 1e-8)   # naive, yuvarlama farkıyla
    assert direction_hits([290.0, 99.0], f, y0) == (0, 0)


def test_mase_is_scale_free():
    # aynı yüzde hatalar: 1 TL'lik fon ve 300 TL'lik hisse eşit ağırlık
    y0 = np.array([1.0, 300.0]); y = y0 * 1.10
    f_good = y0 * 1.05                     # yarı hata
    assert mase(y, f_good, y0) == pytest.approx(0.5)


def test_diebold_mariano_detects_real_difference_and_not_noise():
    from backtest.metrics import diebold_mariano

    rng = np.random.default_rng(0)
    base = rng.uniform(0.02, 0.05, 200)
    stat, p = diebold_mariano(base * 0.8, base, lags=3)       # A her zaman %20 daha iyi
    assert stat < 0 and p < 0.001
    noise = base + rng.normal(0, 0.01, 200)
    _, p2 = diebold_mariano(noise, base + rng.normal(0, 0.01, 200), lags=3)
    assert p2 > 0.05


def test_dm_table_shape():
    from backtest.metrics import dm_table

    rng = np.random.default_rng(1)
    dates = pd.bdate_range("2024-01-01", periods=60).date
    rows = []
    real = {c: 100.0 * np.exp(rng.normal(0, 0.03, 60)) for c in ["A", "B"]}   # gerçekleşen: modelden bağımsız
    for m, k in [("timesfm", 0.9), ("naive", 1.0)]:
        for c in ["A", "B"]:
            y0 = np.full(60, 100.0); y = real[c]
            rows.append(pd.DataFrame({"model": m, "code": c, "type": "stock", "origin_date": dates,
                                      "horizon": 5, "y0": y0, "y": y, "p50": y0 + (y - y0) * (1 - k + 0.0)}))
    t = dm_table(pd.concat(rows), ["timesfm"], ["naive"], by=["type"])
    assert len(t) == 1 and t.iloc[0]["rel_loss"] == pytest.approx(0.9, rel=1e-6)
