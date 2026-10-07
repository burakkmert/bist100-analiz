"""BIST toplayıcı testleri. İnternet gerekmez: yfinance yerine sahte veri kullanılır.

Çalıştırma: pytest data/tests -q
"""
from datetime import date, timedelta
from pathlib import Path
import tempfile

import pandas as pd
import pytest

from data.collectors.bist_list import load_stock_list, to_yahoo
from data.collectors.bist_prices import (
    PRICE_COLUMNS, merge_prices, next_start, normalize_yf_frame, read_cache, run,
)


def fake_yf_frame(start: str, days: int, base: float = 100.0) -> pd.DataFrame:
    """yfinance.download çıktısına benzeyen sahte tablo (MultiIndex sütunlu)."""
    idx = pd.bdate_range(start, periods=days, name="Date")
    cols = pd.MultiIndex.from_product([["Open", "High", "Low", "Close", "Adj Close", "Volume"], ["X.IS"]])
    data = [[base + i, base + i + 1, base + i - 1, base + i, base + i, 1000 + i] for i in range(days)]
    return pd.DataFrame(data, index=idx, columns=cols)


# ---------------------------------------------------------------- bist_list

def test_to_yahoo():
    assert to_yahoo("thyao") == "THYAO.IS"
    assert to_yahoo("THYAO.IS") == "THYAO.IS"


def test_load_stock_list_cleans_and_dedupes():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "s.csv"
        p.write_text("code,name,sector\nthyao,,\nGARAN,Garanti BBVA,Bankacılık\nTHYAO.IS,,\n", encoding="utf-8")
        df = load_stock_list(p)
    assert df["code"].tolist() == ["GARAN", "THYAO"]
    assert df.loc[df.code == "THYAO", "name"].item() == "THYAO"  # boş ad -> kod
    assert set(df["type"]) == {"stock"}


def test_load_stock_list_rejects_bad_code():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "s.csv"
        p.write_text("code,name,sector\nTH-YAO,,\n", encoding="utf-8")
        with pytest.raises(ValueError):
            load_stock_list(p)


def test_repo_stock_list_is_valid():
    df = load_stock_list()
    assert len(df) > 50 and df["code"].is_unique


# ---------------------------------------------------------------- bist_prices

def test_normalize_yf_frame_columns_and_types():
    df = normalize_yf_frame(fake_yf_frame("2026-01-05", 5), "THYAO")
    assert list(df.columns) == PRICE_COLUMNS
    assert len(df) == 5 and set(df["code"]) == {"THYAO"}
    assert isinstance(df["date"].iloc[0], date)


def test_normalize_empty():
    assert normalize_yf_frame(pd.DataFrame(), "X").empty


def test_merge_prices_upsert_new_wins():
    old = normalize_yf_frame(fake_yf_frame("2026-01-05", 5, base=100), "X")
    new = normalize_yf_frame(fake_yf_frame("2026-01-08", 5, base=200), "X")  # 2 gün çakışır
    merged = merge_prices(old, new)
    assert merged["date"].is_unique
    assert len(merged) == 8
    assert merged.loc[merged.date == date(2026, 1, 8), "close"].item() == 200  # yeni kazandı


def test_next_start_incremental():
    default = date(2021, 1, 1)
    assert next_start(pd.DataFrame(columns=PRICE_COLUMNS), default) == default
    old = normalize_yf_frame(fake_yf_frame("2026-01-05", 5), "X")
    assert next_start(old, default) == max(old["date"]) - timedelta(days=3)


def test_run_is_idempotent_and_continues_on_error():
    def fake_fetch(code, start):
        if code == "BOZUK":
            raise RuntimeError("bağlantı hatası")
        return normalize_yf_frame(fake_yf_frame("2026-01-05", 10), code)

    with tempfile.TemporaryDirectory() as d:
        cache = Path(d)
        r1 = run(["THYAO", "BOZUK", "GARAN"], years=1, cache_dir=cache, fetch=fake_fetch)
        r2 = run(["THYAO"], years=1, cache_dir=cache, fetch=fake_fetch)  # tekrar çalıştır
        thyao = read_cache("THYAO", cache)

    assert r1.set_index("code").loc["BOZUK", "error"] == "bağlantı hatası"
    assert r1.set_index("code").loc["GARAN", "new_rows"] == 10  # hatadan sonra devam etti
    assert r2.loc[0, "new_rows"] == 0  # ikinci kez satır eklenmedi
    assert len(thyao) == 10 and thyao["date"].is_unique
