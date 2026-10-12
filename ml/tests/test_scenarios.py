"""Senaryo testleri. Çalıştırma: pytest ml/tests -q"""
from datetime import date

import numpy as np
import pandas as pd

from ml.scenarios import SCENARIO_COLUMNS, build_scenarios, combine, evaluate_on_backtest, model_weights

RD = date(2026, 10, 11)


def fc(rows):
    return pd.DataFrame(rows, columns=["code", "run_date", "model", "horizon", "p10", "p50", "p90"])


def test_30d_is_weighted_by_inverse_mae():
    f = fc([("X", RD, "timesfm", 30, 90, 100, 110), ("X", RD, "naive", 30, 80, 90, 100)])
    errors = pd.DataFrame({"code": "X", "horizon": 30, "model": ["timesfm", "naive"], "mae": [1.0, 3.0]})
    sc = build_scenarios(f, errors, ["timesfm", "naive"])
    r = sc.iloc[0]
    # ağırlık 0.75 / 0.25
    assert np.isclose(r.base, 0.75 * 100 + 0.25 * 90) and np.isclose(r.bear, 0.75 * 90 + 0.25 * 80)


def test_equal_weights_without_errors():
    f = fc([("X", RD, "timesfm", 30, 90, 100, 110), ("X", RD, "naive", 30, 80, 90, 100)])
    r = build_scenarios(f, None, ["timesfm", "naive"]).iloc[0]
    assert np.isclose(r.base, 95) and np.isclose(r.bull, 105)


def test_120d_band_widened_and_no_point_needed():
    # modeller dar bant veriyor; naive_drift oynaklık bandı daha geniş -> genişletilir. p50 yok (NULL).
    f = fc([("F", RD, "timesfm", 120, 98, np.nan, 104), ("F", RD, "naive_drift", 120, 90, np.nan, 125)])
    r = build_scenarios(f, None, ["timesfm", "naive_drift"]).iloc[0]
    assert r.horizon == 120 and np.isclose(r.bear, min(94.0, 90)) and np.isclose(r.bull, max(114.5, 125))
    assert np.isclose(r.base, np.sqrt(r.bear * r.bull)) and r.bear <= r.base <= r.bull
    assert list(build_scenarios(f, None, ["timesfm", "naive_drift"]).columns) == SCENARIO_COLUMNS


def test_weights_sum_to_one():
    e = pd.DataFrame({"code": "X", "horizon": 30, "model": ["a", "b", "c"], "mae": [1, 2, 4]})
    w = model_weights(e, ["a", "b", "c"])
    assert np.isclose(w["w"].sum(), 1.0) and w.set_index("model")["w"]["a"] > w.set_index("model")["w"]["c"]


def test_evaluate_on_backtest_reports_scenario_and_models():
    from backtest.walk_forward import run_walk_forward
    from ml.models.baselines import NaiveDriftForecaster, NaiveForecaster

    rng = np.random.default_rng(0)
    frames = {c: pd.DataFrame({"date": pd.bdate_range("2023-01-02", periods=500).date,
                               "price": 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, 500)))}) for c in "AB"}
    raw, _ = run_walk_forward(frames, [NaiveForecaster(), NaiveDriftForecaster()], [30, 120], 300, 10, 120, 512,
                              log=lambda *a: None)
    t = evaluate_on_backtest(raw, ["naive", "naive_drift"])
    sc = t[t.model == "senaryo"].set_index("horizon")
    nd = t[t.model == "naive_drift"].set_index("horizon")
    assert set(sc.index) == {30, 120}
    assert sc.loc[120, "width_pct"] >= nd.loc[120, "width_pct"] - 1e-9   # 120 bandı en az oynaklık bandı kadar geniş


def test_negative_lower_bound_is_floored():
    f = fc([("Z", RD, "timesfm", 120, -5, np.nan, 50), ("Z", RD, "naive_drift", 120, -10, np.nan, 60)])
    r = build_scenarios(f, None, ["timesfm", "naive_drift"]).iloc[0]
    assert r.bear > 0 and np.isfinite(r.base) and r.bear <= r.base <= r.bull


def test_default_models_exclude_plain_naive():
    from ml.scenarios import DEFAULT_MODELS
    assert "naive" not in DEFAULT_MODELS and "naive_drift" in DEFAULT_MODELS
