"""run_engine'in saf kısmı (veritabanısız): gruplama, tüm varlıkları işleme, hata eşiği.
Veritabanıyla uçtan uca test: backend/tests/test_run_engine_db.py (CI)."""

from datetime import date

import numpy as np
import pandas as pd

from engine import decision as dec
from engine import run_engine as re_

CFG = dec.load_config()
RD = date(2026, 10, 13)


def _prices(code, n=300, drift=0.0008, seed=0, ohlc=True):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(drift, 0.015, n)))
    d = pd.DataFrame(
        {"code": code, "date": pd.bdate_range(end=RD, periods=n).date, "close": close, "adj_close": close}
    )
    if ohlc:
        d["open"], d["high"], d["low"], d["volume"] = close, close * 1.01, close * 0.99, 3e6
    else:
        d[["open", "high", "low", "volume"]] = np.nan
    return d


def _fc(code, last, models=("timesfm", "chronos", "naive_drift")):
    rows = []
    for h in (1, 5, 20):
        for i, m in enumerate(models):
            mid = last * (1 + 0.01 * h**0.5 + 0.002 * i)
            rows.append(
                {"code": code, "model": m, "horizon": h, "p10": mid * 0.95, "p50": mid, "p90": mid * 1.05}
            )
    return rows


def _inputs():
    prices = pd.concat(
        [
            _prices("AAA", seed=1),
            _prices("FON", seed=2, ohlc=False),
            _prices("KISA", n=30, seed=3),
            _prices("XU100", seed=4),
        ],
        ignore_index=True,
    )
    last = {c: float(g["close"].iloc[-1]) for c, g in prices.groupby("code")}
    fc = pd.DataFrame(_fc("AAA", last["AAA"]) + _fc("FON", last["FON"]) + _fc("KISA", last["KISA"]))
    err = pd.DataFrame(
        [
            {"code": "AAA", "model": "timesfm", "horizon": 5, "mae": 1.0},
            {"code": "AAA", "model": "chronos", "horizon": 5, "mae": 3.0},
        ]
    )
    assets = {"AAA": "stock", "FON": "fund", "KISA": "stock", "TAHMINSIZ": "stock"}
    return assets, prices, fc, err


def test_gruplama():
    _, _, fc, err = _inputs()
    g = re_.group_forecasts(fc)
    assert set(g["AAA"]) == {1, 5, 20} and set(g["AAA"][5]) == {"timesfm", "chronos", "naive_drift"}
    assert re_.group_errors(err)["AAA"][5] == {"timesfm": 1.0, "chronos": 3.0}


def test_tum_varliklar_islenir_ve_atlananlar_sayilir():
    rows, stats = re_.analyze_all(RD, *_inputs(), CFG)
    assert stats["ok"] == 2  # AAA ve FON
    assert stats["skipped_short_history"] == 1  # KISA (30 gün)
    assert stats["skipped_no_forecast"] == 1  # TAHMINSIZ
    assert stats["failed"] == []
    assert stats["rows"] == len(rows) == 6  # 2 varlık × 3 ufuk
    assert sum(stats["directions"].values()) == 6
    assert stats["market_regime"] in ("trend", "range", "high_vol")
    assert all(r["indicators"]["market_regime"] == stats["market_regime"] for r in rows)
    assert not re_.is_failure(stats)


def test_hata_agirliklari_kullanilir():
    rows, _ = re_.analyze_all(RD, *_inputs(), CFG)
    w = next(r["weights"] for r in rows if r["code"] == "AAA" and r["horizon"] == 5)
    assert w["timesfm"] > w["chronos"]  # MAE 1 < 3


def test_bir_varlikta_hata_digerlerini_durdurmaz(monkeypatch):
    real = dec.analyze

    def bozuk(code, *a, **k):
        if code == "AAA":
            raise RuntimeError("bozuk veri")
        return real(code, *a, **k)

    monkeypatch.setattr(dec, "analyze", bozuk)
    rows, stats = re_.analyze_all(RD, *_inputs(), CFG)
    assert [f["code"] for f in stats["failed"]] == ["AAA"]
    assert {r["code"] for r in rows} == {"FON"}
    assert re_.is_failure(stats)  # 2 varlıktan 1'i (%50) > %10


def test_hic_satir_yoksa_basarisiz():
    assert re_.is_failure({"ok": 0, "failed": [], "rows": 0})
    assert not re_.is_failure({"ok": 100, "failed": [{"code": "X"}] * 5, "rows": 300})
