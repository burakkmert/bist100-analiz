"""XU100'ün assets/prices satırları (type='index'): internet ve DB gerekmez."""
import numpy as np
import pandas as pd

from data.run_daily import index_frames


def px_frame(n: int) -> pd.DataFrame:
    close = 10000 + np.arange(n, dtype=float)
    return pd.DataFrame({"code": "XU100", "date": pd.bdate_range("2024-01-01", periods=n).date,
                         "open": close, "high": close, "low": close, "close": close,
                         "adj_close": np.nan, "volume": 1e9})


def test_index_frames_builds_index_asset_and_fills_adj_close():
    asset, prices = index_frames(px_frame(200))
    row = asset.iloc[0]
    assert row["code"] == "XU100" and row["type"] == "index" and row["min_history_ok"]
    assert prices["adj_close"].notna().all() and (prices["adj_close"] == prices["close"]).all()


def test_index_frames_drops_bad_rows_and_flags_short_history():
    px = pd.concat([px_frame(50), px_frame(50).iloc[:1].assign(close=0.0)], ignore_index=True)
    asset, prices = index_frames(px)
    assert len(prices) == 50 and not asset.iloc[0]["min_history_ok"]


def test_index_frames_empty_cache():
    asset, prices = index_frames(pd.DataFrame(columns=["code", "date", "open", "high", "low", "close", "adj_close", "volume"]))
    assert prices.empty and asset.iloc[0]["code"] == "XU100" and not asset.iloc[0]["min_history_ok"]
