"""Walk-forward testleri — en önemlisi: model geleceği GÖRMÜYOR mu?

Çalıştırma: pytest backtest/tests -q
"""
import numpy as np
import pandas as pd

from backtest.walk_forward import build_contexts, origin_indices, run_walk_forward
from ml.models.base import Forecaster
from ml.models.baselines import NaiveForecaster

HORIZONS = [1, 5, 20]


def frame(n=400, seed=0):
    rng = np.random.default_rng(seed)
    px = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    return pd.DataFrame({"date": pd.bdate_range("2023-01-02", periods=n).date, "price": px})


def test_origin_indices_weekly_within_test_window():
    idx = origin_indices(n=400, test_days=100, step=5, min_context=120)
    assert idx[-1] == 398 and all(b - a == 5 for a, b in zip(idx, idx[1:]))
    assert idx[0] >= 400 - 1 - 100
    assert origin_indices(n=100, test_days=50, step=5, min_context=120) == []   # bağlam yetmez


class Spy(Forecaster):
    """Kendisine verilen bağlamın son değerini kaydeder ve onu tahmin eder (naive gibi)."""
    name = "spy"

    def __init__(self):
        self.seen = {}

    def _predict(self, series, horizons):
        self.seen.update({k: v[-1] for k, v in series.items()})
        return NaiveForecaster()._predict(series, horizons)


def test_no_lookahead():
    frames = {"X": frame()}
    spy = Spy()
    res, _ = run_walk_forward(frames, [spy], HORIZONS, test_days=100, step=5, min_context=120,
                              context_length=512, log=lambda *a: None)
    px = frames["X"]["price"].to_numpy()
    for key, last_seen in spy.seen.items():
        t = int(key.split("|")[1])
        assert np.isclose(last_seen, px[t], rtol=1e-6)    # model t gününden sonrasını görmedi (float32)
    # gerçekleşen değer gerçekten t+h günü
    r = res.iloc[0]
    t = frames["X"]["date"].tolist().index(r.origin_date)
    assert r.y == px[t + r.horizon] and r.y0 == px[t]


def test_context_length_is_respected():
    contexts, _ = build_contexts({"X": frame()}, test_days=50, step=5, min_context=120, context_length=64)
    assert max(len(v) for v in contexts.values()) == 64


def test_horizon_beyond_data_is_dropped():
    frames = {"X": frame(300)}
    res, _ = run_walk_forward(frames, [NaiveForecaster()], HORIZONS, test_days=60, step=5,
                              min_context=120, context_length=512, log=lambda *a: None)
    last = frames["X"]["date"].iloc[-1]
    assert (res["target_date"] <= last).all()
    assert res.groupby("horizon").size()[1] > res.groupby("horizon").size()[20]


def test_naive_mase_is_exactly_one():
    from backtest.metrics import summarize_by

    frames = {c: frame(seed=i) for i, c in enumerate(["A", "B", "C"])}
    res, _ = run_walk_forward(frames, [NaiveForecaster()], HORIZONS, test_days=150, step=5,
                              min_context=120, context_length=512, log=lambda *a: None)
    table = summarize_by(res, ["model", "horizon"])
    assert np.allclose(table["mase"], 1.0)
