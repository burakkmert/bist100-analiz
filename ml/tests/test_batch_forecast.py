"""Gece tahmin işi testleri: sahte modeller ve sahte önbellek; internet/GPU/DB gerekmez.

Çalıştırma: pytest ml/tests -q
"""
from datetime import date

import numpy as np
import pandas as pd

from ml.batch_forecast import FORECAST_COLUMNS, load_series, run
from ml.models.baselines import NaiveForecaster
from ml.models.base import Forecaster

HORIZONS = [1, 5, 20, 30, 120]
RUN_DATE = date(2026, 10, 9)


def prices_frame(n: int, start: float = 100.0) -> pd.DataFrame:
    px = start * np.exp(np.cumsum(np.full(n, 0.001)))
    return pd.DataFrame({"date": pd.bdate_range("2021-01-04", periods=n).date,
                         "close": px, "adj_close": px})


class BrokenOnOne(Forecaster):
    """Toplu çağrıda hata verir; 'BOZUK' varlığında tekil çağrıda da hata verir."""
    name = "broken_on_one"

    def _predict(self, series, horizons):
        if len(series) > 1 or "BOZUK" in series:
            raise RuntimeError("sahte hata")
        return NaiveForecaster()._predict(series, horizons)


class AlwaysFails(Forecaster):
    name = "always_fails"

    def _predict(self, series, horizons):
        raise RuntimeError("model yüklenemedi")


def test_load_series_skips_missing_and_short():
    store = {"OK": prices_frame(300), "KISA": prices_frame(50), "BOS": pd.DataFrame()}
    series, skipped = load_series(["OK", "KISA", "BOS", "YOK"], 120, reader=lambda c: store.get(c, pd.DataFrame()))
    assert list(series) == ["OK"]
    assert set(skipped) == {"KISA", "BOS", "YOK"}
    assert "kısa geçmiş" in skipped["KISA"]


def test_run_writes_contract_rows_and_nulls_120_p50():
    series = {c: prices_frame(300)["close"].to_numpy() for c in ["THYAO", "IPB"]}
    out, stats = run(series, [NaiveForecaster()], HORIZONS, RUN_DATE)
    assert list(out.columns) == FORECAST_COLUMNS
    assert len(out) == 2 * len(HORIZONS)
    assert set(out["run_date"]) == {RUN_DATE} and set(out["model"]) == {"naive"}
    h120 = out[out["horizon"] == 120]
    assert h120["p50"].isna().all() and h120["p10"].notna().all()  # bant var, nokta tahmin yok
    assert out[out["horizon"] < 120]["p50"].notna().all()
    assert stats[0]["status"] == "ok"


def test_run_survives_failures():
    series = {c: prices_frame(300)["close"].to_numpy() for c in ["A", "BOZUK", "C"]}
    out, stats = run(series, [BrokenOnOne(), AlwaysFails(), NaiveForecaster()], HORIZONS, RUN_DATE)
    s = {x["model"]: x for x in stats}
    assert s["broken_on_one"]["status"] == "partial"
    assert set(s["broken_on_one"]["errors"]) == {"BOZUK"}
    assert s["always_fails"]["status"] == "failed"
    assert s["naive"]["status"] == "ok"           # önceki modeller çökse de devam etti
    assert set(out[out.model == "broken_on_one"]["code"]) == {"A", "C"}
