"""Fon trend araması testleri: sentetik fon serileri; internet/GPU/DB gerekmez."""
import numpy as np
import pandas as pd

from backtest import drift_search as ds
from backtest.walk_forward import run_walk_forward
from ml.models.baselines import NaiveDriftForecaster


def fund_frame(n: int, mu: float, seed: int, vol: float = 0.002) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    px = 100 * np.exp(np.cumsum(rng.normal(mu, vol, n)))
    return pd.DataFrame({"date": pd.bdate_range("2022-01-03", periods=n).date, "price": px})


def test_baseline_variant_equals_production_naive_drift():
    px = fund_frame(400, 0.0008, 1)["price"].to_numpy()
    prod = NaiveDriftForecaster().center(px, 20)
    base = ds.DampedDrift(250, 1.0).center(px, 20)
    assert abs(prod - base) < 1e-9
    assert ds.DampedDrift(250, 1.0).name == ds.BASELINE


def test_shrink_pulls_forecast_toward_last_price():
    px = fund_frame(400, 0.001, 2)["price"].to_numpy()
    full, half = ds.DampedDrift(120, 1.0).center(px, 20), ds.DampedDrift(120, 0.5).center(px, 20)
    assert px[-1] < half < full


def test_small_categories_are_merged():
    cats = pd.Series({f"A{i}": "serbest" for i in range(20)} | {f"B{i}": "fon_sepeti" for i in range(5)})
    out = ds.assign_categories(list(cats.index), cats, min_funds=15)
    assert set(out.values()) == {"serbest", "diger"}


def test_pipeline_selects_on_train_and_tests_on_test():
    # Yarı fon sabit güçlü trendli, yarısı trendsiz gürültü: kategori A (trendli), B (trendsiz)
    frames = {f"A{i}": fund_frame(700, 0.001, i) for i in range(15)}
    frames |= {f"B{i}": fund_frame(700, 0.0, 100 + i, 0.01) for i in range(15)}
    models = ds.make_variants(windows=[20, 250], shrinks=[0.5, 1.0])
    raw, _ = run_walk_forward(frames, models, [5, 20], test_days=500, step=10, min_context=120,
                              context_length=512, log=lambda *_: None)
    cats = {c: ("A" if c.startswith("A") else "B") for c in frames}
    raw["category"] = raw["code"].map(cats)
    train, test = ds.time_split(raw)
    assert pd.to_datetime(train["origin_date"]).max() < pd.to_datetime(test["origin_date"]).min()
    chosen = ds.select_best(train)
    assert set(chosen["category"]) == {"A", "B"} and set(chosen["selected"]) <= {m.name for m in models}
    # Trendsiz gürültülü grupta yumuşatma (s50) kazanmalı: trend uydurmak zarar verir
    b = chosen[chosen["category"] == "B"]["selected"]
    assert b.str.endswith("_s50").all()
    ds.BASELINE = "w250_s100"
    res = ds.test_selection(test, chosen, step=10)
    assert {"category", "horizon", "rel_loss", "p_value", "oneri"} <= set(res.columns) and len(res) > 0
    ov = ds.overall(test, chosen, step=10)
    assert len(ov) == 2
