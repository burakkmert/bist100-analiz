"""Model sarmalayıcı testleri. Gerçek modeller indirilmez: TimesFM/Chronos için sahte
nesneler kullanılır; böylece dizin ve biçim mantığı internet ve GPU olmadan test edilir.

Çalıştırma: pytest ml/tests -q
"""
import numpy as np
import pytest

from ml.models.base import OUTPUT_COLUMNS, clean_series
from ml.models.baselines import ArimaForecaster, MovingAverageForecaster, NaiveForecaster
from ml.models.chronos_model import ChronosForecaster
from ml.models.timesfm_model import TimesFMForecaster

HORIZONS = [1, 5, 20, 30, 120]


def random_walk(n=600, start=100.0, seed=0):
    rng = np.random.default_rng(seed)
    return (start * np.exp(np.cumsum(rng.normal(0, 0.02, n)))).astype("float32")


def check_output(df, codes):
    assert list(df.columns) == OUTPUT_COLUMNS
    assert len(df) == len(codes) * len(HORIZONS)
    assert set(df["code"]) == set(codes)
    assert (df["p10"] <= df["p50"]).all() and (df["p50"] <= df["p90"]).all()
    assert (df[["p10", "p50", "p90"]] > 0).all().all()


# ---------------------------------------------------------------- yardımcılar

def test_clean_series_drops_bad_values():
    out = clean_series([1.0, np.nan, 0, -5, 2.0, np.inf])
    assert out.tolist() == [1.0, 2.0] and out.dtype == np.float32


# ---------------------------------------------------------------- baseline'lar

def test_naive_center_is_last_price_and_widens():
    s = random_walk()
    df = NaiveForecaster().predict({"X": s}, HORIZONS)
    check_output(df, ["X"])
    assert np.allclose(df["p50"], s[-1])
    width = (df["p90"] - df["p10"]).to_numpy()
    assert (np.diff(width) > 0).all()  # ufuk büyüdükçe aralık genişler


def test_moving_average_center():
    s = random_walk()
    df = MovingAverageForecaster(window=20).predict({"X": s}, HORIZONS)
    check_output(df, ["X"])
    assert np.isclose(df["p50"].iloc[0], s[-20:].mean(), rtol=1e-5)


def test_baselines_skip_too_short_series():
    df = NaiveForecaster().predict({"OK": random_walk(), "BOS": np.array([np.nan, 5.0])}, HORIZONS)
    assert set(df["code"]) == {"OK"}


def test_arima_runs_or_falls_back():
    pytest.importorskip("statsmodels")
    df = ArimaForecaster().predict({"A": random_walk(seed=1), "B": random_walk(seed=2)}, HORIZONS)
    check_output(df, ["A", "B"])


# ---------------------------------------------------------------- TimesFM (sahte model)

class FakeTimesFM:
    """forecast(): (seri, ufuk, 10) kantil; k. kantil = son fiyat * (1 + (k-5)*0.01*√h)."""

    def __init__(self):
        self.calls = []

    def forecast(self, horizon, inputs):
        self.calls.append(len(inputs))
        n = len(inputs)
        last = np.array([x[-1] for x in inputs])[:, None, None]
        h = np.sqrt(np.arange(1, horizon + 1))[None, :, None]
        k = np.arange(10)[None, None, :]
        q = last * (1 + (k - 5) * 0.01 * h)
        q[..., 0] = last[..., 0]  # 0: ortalama
        return q[..., 5], q


def test_timesfm_wrapper_picks_q10_q50_q90_and_batches():
    fake = FakeTimesFM()
    series = {f"S{i}": random_walk(seed=i) for i in range(5)}
    df = TimesFMForecaster(batch_size=2, model=fake, device="cpu").predict(series, HORIZONS)
    check_output(df, list(series))
    assert fake.calls == [2, 2, 1]
    row = df[(df.code == "S0") & (df.horizon == 1)].iloc[0]
    last = series["S0"][-1]
    assert np.isclose(row.p50, last) and np.isclose(row.p10, last * 0.96) and np.isclose(row.p90, last * 1.04)


def test_timesfm_rejects_too_long_horizon():
    with pytest.raises(ValueError):
        TimesFMForecaster(max_horizon=128, model=FakeTimesFM(), device="cpu").predict(
            {"X": random_walk()}, [200])


# ---------------------------------------------------------------- Chronos (sahte pipeline)

class FakeChronos:
    def predict_quantiles(self, inputs, prediction_length, quantile_levels, **kw):
        out = []
        for x in inputs:
            base = np.full((1, prediction_length, 3), x[-1], dtype="float32")
            base[..., 0] *= 0.95
            base[..., 2] *= 1.05
            out.append(base)
        return out, [b[..., 1] for b in out]


def test_chronos_wrapper_shapes():
    series = {"IPB": random_walk(seed=3), "THYAO": random_walk(seed=4)}
    df = ChronosForecaster(batch_size=1, pipeline=FakeChronos(), device="cpu").predict(series, HORIZONS)
    check_output(df, list(series))
    row = df[(df.code == "IPB") & (df.horizon == 120)].iloc[0]
    assert np.isclose(row.p10, series["IPB"][-1] * 0.95, rtol=1e-5)
