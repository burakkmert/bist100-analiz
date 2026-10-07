"""Temizleme, doğrulama ve gece işi testleri. İnternet ve veritabanı gerekmez.

Çalıştırma: pytest data/tests -q
"""
from datetime import date, timedelta
from pathlib import Path
import tempfile

import pandas as pd

from data.cleaning import clean_prices, market_calendar, missing_days
from data.validate import build_report, validate_assets


def make_prices(code: str, n: int, start: date = date(2026, 1, 5), base: float = 100.0,
                skip: set[int] = frozenset(), fund: bool = False) -> pd.DataFrame:
    days = [d.date() for d in pd.bdate_range(start, periods=n)]
    rows = []
    for i, d in enumerate(days):
        if i in skip:
            continue
        px = base + i * 0.5
        rows.append({"code": code, "date": d,
                     "open": None if fund else px, "high": None if fund else px + 1,
                     "low": None if fund else px - 1, "close": px, "adj_close": px,
                     "volume": None if fund else 1000})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- cleaning

def test_clean_removes_nonpositive_and_duplicates_flags_jumps():
    df = make_prices("X", 10)
    df.loc[3, ["close", "adj_close"]] = 0          # sıfır fiyat
    df.loc[6, ["close", "adj_close"]] = 300        # büyük sıçrama
    df = pd.concat([df, df.iloc[[8]]])             # çift kayıt
    clean, issues = clean_prices(df)
    assert len(clean) == 9 and clean["date"].is_unique
    assert (clean["close"] > 0).all()
    assert set(issues["issue"]) == {"nonpositive_price", "jump"}
    assert len(clean) == 9  # sıçrama silinmez, yalnızca işaretlenir


def test_clean_uses_adj_close_for_jumps():
    df = make_prices("X", 5)
    df.loc[3:, "close"] = df.loc[3:, "close"] / 2  # bölünme: close yarıya iner, adj_close düzgün
    _, issues = clean_prices(df)
    assert issues.empty


def test_market_calendar_and_missing_days():
    a = make_prices("A", 10)
    b = make_prices("B", 10, skip={4})
    c = make_prices("C", 10, skip={7})
    cal = market_calendar([a, b, c])
    assert len(cal) == 10                          # her gün varlıkların çoğunda var
    assert missing_days(b, cal) == [cal[4]]
    assert missing_days(c, cal) == [cal[7]]
    # tek varlıkta görülen gün (ör. hatalı tatil kaydı) takvime girmez
    odd = pd.concat([a, pd.DataFrame([{**a.iloc[0].to_dict(), "date": date(2026, 1, 3)}])])
    assert date(2026, 1, 3) not in market_calendar([odd, b, c])


# ---------------------------------------------------------------- validate

def test_validate_and_report():
    frames = {
        "OLD": make_prices("OLD", 200),
        # kısa geçmiş: OLD ile aynı gün biter, yalnızca 50 gün
        "IPO": make_prices("IPO", 50, start=pd.bdate_range("2026-01-05", periods=200)[150].date()),
        "STALE": make_prices("STALE", 190),                       # 10 gün geride
        "FND": make_prices("FND", 200, fund=True),
    }
    types = {"OLD": "stock", "IPO": "stock", "STALE": "stock", "FND": "fund"}
    _, summary, _ = validate_assets(frames, types)
    s = summary.set_index("code")
    assert bool(s.loc["OLD", "min_history_ok"]) and not bool(s.loc["IPO", "min_history_ok"])
    assert not bool(s.loc["STALE", "up_to_date"]) and bool(s.loc["FND", "up_to_date"])

    report = build_report(summary, collect_errors=["BOZUK"], run_date=date(2026, 10, 7))
    assert report["stocks"] == 3 and report["funds"] == 1
    assert report["stale"] == ["STALE"] and report["short_history"] == ["IPO"]
    assert report["collect_errors"] == ["BOZUK"]


# ---------------------------------------------------------------- run_daily (uçtan uca)

def test_run_daily_end_to_end_without_network():
    import data.run_daily as rd

    store: dict[str, pd.DataFrame] = {}
    collected = {}

    def fake_bist_run(codes, years):
        collected["bist"] = list(codes)
        for c in codes:
            store[c] = make_prices(c, 150)
        return pd.DataFrame({"code": codes, "error": [None] * len(codes)})

    def fake_tefas_run(codes):
        collected["tefas"] = list(codes)
        for c in codes:
            store[c] = make_prices(c, 150, fund=True)
        return pd.DataFrame({"code": codes, "error": ["TEFAS hatası" if c == "BOZUK" else None for c in codes]})

    originals = (rd.bist_prices.run, rd.tefas_prices.run, rd.read_cache, rd.write_cache, rd.write_report)
    with tempfile.TemporaryDirectory() as d:
        rd.bist_prices.run, rd.tefas_prices.run = fake_bist_run, fake_tefas_run
        rd.read_cache = lambda c: store.get(c, pd.DataFrame(columns=["code", "date", "close", "adj_close"]))
        rd.write_cache = lambda df, c: store.__setitem__(c, df)
        rd.write_report = lambda rep, s, i: (Path(d) / "r.json")
        try:
            ok = rd.main(["--stocks", "THYAO", "GARAN", "--funds", "IPB"])
            fail = rd.main(["--stocks", "THYAO", "--funds", "BOZUK", "--max-error-rate", "0.1"])
        finally:
            (rd.bist_prices.run, rd.tefas_prices.run, rd.read_cache,
             rd.write_cache, rd.write_report) = originals

    assert ok == 0 and fail == 1
    assert "XU100" in collected["bist"]            # endeks de çekiliyor
    assert collected["tefas"] == ["BOZUK"]
