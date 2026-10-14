import numpy as np
import pandas as pd

from backtest.subset_check import assign_subsets, liquidity_stats, subset_dm


def _prices(flat_share: float, vol: float, n=300, seed=0):
    rng = np.random.default_rng(seed)
    r = rng.normal(0, 0.01, n)
    r[rng.random(n) < flat_share] = 0.0
    return pd.DataFrame({"date": pd.date_range("2024-01-01", periods=n), "close": 100 * np.exp(np.cumsum(r)),
                         "volume": vol})


def test_liquidity_stats_zero_return_share():
    st = liquidity_stats(_prices(0.5, 1000))
    assert 0.35 < st["zero_ret"] < 0.65
    assert st["turnover"] > 0


def test_assign_subsets_partitions():
    stats = pd.DataFrame({"turnover": [10, 5, 1, 0.5], "zero_ret": [0.0, 0.01, 0.2, 0.3]},
                         index=["A", "B", "C", "D"])
    s = assign_subsets(stats, top_n=2)
    assert s["likit100"] == ["A", "B"] and s["likit_disi"] == ["C", "D"]
    assert s["sik_islem"] == ["A", "B"] and s["seyrek"] == ["C", "D"]


def test_subset_dm_runs_on_synthetic():
    rows = []
    for code in ["A", "B"]:
        for o in pd.date_range("2025-01-01", periods=40, freq="5D"):
            for m, bias in [("timesfm", 1.0), ("naive_drift", 0.0)]:
                rows.append({"model": m, "code": code, "origin_date": o, "horizon": 5, "y0": 100.0,
                             "y": 101.0 + (hash((code, o)) % 3), "p50": 100.5 + bias})
    out = subset_dm(pd.DataFrame(rows), {"k": ["A", "B"]}, step=5)
    assert list(out["kesit"].unique()) == ["k"] and out["n_hisse"].iloc[0] == 2
