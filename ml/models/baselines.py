"""Basit kıyas modelleri (Görev 4): naive, hareketli ortalama, ARIMA.

TimesFM ve Chronos'un gerçekten bir şey kattığını göstermek için bunları geçmeleri gerekir.

Aralık (p10/p90) nasıl üretiliyor?
- Naive ve MA: serinin kendi geçmişindeki h günlük log-getirilerin ampirik %10/%90 dilimleri,
  medyanı sıfıra çekilerek merkez tahmine eklenir. Böylece yalnızca "yayılım" geçmişten gelir,
  yön bilgisi eklenmez.
- ARIMA: modelin kendi %80 güven aralığı (log fiyat üzerinde).
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from ml.models.base import OUTPUT_COLUMNS, Forecaster


def empirical_spread(prices: np.ndarray, h: int, window: int) -> tuple[float, float]:
    """h günlük log-getirilerin medyana göre %10 ve %90 sapmaları. Geçmiş yetmezse
    günlük oynaklık √h ile ölçeklenir."""
    logp = np.log(prices[-(window + h):])
    if len(logp) > h + 20:
        r = logp[h:] - logp[:-h]
        med = np.median(r)
        return float(np.quantile(r, 0.1) - med), float(np.quantile(r, 0.9) - med)
    daily = np.diff(np.log(prices))
    sigma = float(np.std(daily)) if len(daily) > 1 else 0.0
    z = 1.2816  # standart normalde %90 dilimi
    return -z * sigma * np.sqrt(h), z * sigma * np.sqrt(h)


class _CenterSpreadForecaster(Forecaster):
    """Merkez tahmin + ampirik yayılım şablonu."""

    def __init__(self, spread_window: int = 500):
        self.spread_window = spread_window

    def center(self, prices: np.ndarray, h: int) -> float:
        raise NotImplementedError

    def _predict(self, series, horizons):
        rows = []
        for code, prices in series.items():
            for h in horizons:
                c = self.center(prices, h)
                lo, hi = empirical_spread(prices, h, self.spread_window)
                rows.append({"code": code, "horizon": h,
                             "p10": c * np.exp(lo), "p50": c, "p90": c * np.exp(hi)})
        return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)


class NaiveForecaster(_CenterSpreadForecaster):
    """Yarın = bugün. Finansal serilerde yenmesi şaşırtıcı derecede zor."""

    name = "naive"

    def center(self, prices, h):
        return float(prices[-1])


class MovingAverageForecaster(_CenterSpreadForecaster):
    """Merkez = son `window` günün ortalaması."""

    name = "ma"

    def __init__(self, window: int = 20, spread_window: int = 500):
        super().__init__(spread_window)
        self.window = window

    def center(self, prices, h):
        return float(np.mean(prices[-self.window:]))


class ArimaForecaster(Forecaster):
    """Log fiyat üzerinde ARIMA(p,d,q). Başarısız olursa o seri için naive'e düşer."""

    name = "arima"

    def __init__(self, order: tuple[int, int, int] = (1, 1, 1), max_context: int = 512,
                 spread_window: int = 500):
        self.order = tuple(order)
        self.max_context = max_context
        self._fallback = NaiveForecaster(spread_window)

    def _predict(self, series, horizons):
        from statsmodels.tsa.arima.model import ARIMA

        max_h = max(horizons)
        rows, failed = [], {}
        for code, prices in series.items():
            y = np.log(prices[-self.max_context:].astype("float64"))
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    fit = ARIMA(y, order=self.order).fit()
                    fc = fit.get_forecast(max_h)
                    mean = np.asarray(fc.predicted_mean)
                    ci = np.asarray(fc.conf_int(alpha=0.2))  # %80 aralık
                for h in horizons:
                    rows.append({"code": code, "horizon": h, "p10": float(np.exp(ci[h - 1, 0])),
                                 "p50": float(np.exp(mean[h - 1])), "p90": float(np.exp(ci[h - 1, 1]))})
            except Exception:
                failed[code] = prices
        if failed:
            rows += self._fallback._predict(failed, horizons).to_dict("records")
        return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
