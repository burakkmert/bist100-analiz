"""GET /backtest/summary — model ve baseline metrikleri (Görev 4; veri Kişi 1'in model_errors tablosu).

Her (model, ufuk) için son hesaplama gününün (as_of) değerleri tüm varlıklar üzerinden özetlenir:
  mape (ortalama ve medyan, %), dir_acc (yön isabeti, 0..1),
  beats_naive: modelin MAPE'si 'naive' baseline'ından düşük olan varlıkların oranı (0..1).
MAE fiyat biriminde olduğu için varlıklar arası ortalaması anlamsızdır; özetlenmez.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.db import get_db

router = APIRouter(tags=["assets"], dependencies=[Depends(get_current_user)])

BASELINES = ("naive", "naive_drift")


class ModelMetric(BaseModel):
    model: str
    horizon: int
    is_baseline: bool
    n_assets: int
    mape: float | None
    mape_median: float | None
    dir_acc: float | None
    beats_naive: float | None


class BacktestSummary(BaseModel):
    as_of: date | None
    window_days: int
    asset_type: str | None
    metrics: list[ModelMetric]


_SQL = text(
    """
WITH e AS (
    SELECT me.* FROM model_errors me
    JOIN assets a ON a.code = me.code
    WHERE me.window_days = CAST(:w AS integer)
      AND (CAST(:t AS text) IS NULL OR a.type = CAST(:t AS text))
      AND me.as_of = (SELECT max(as_of) FROM model_errors WHERE window_days = CAST(:w AS integer))
)
SELECT e.as_of, e.model, e.horizon, count(*) AS n_assets,
       avg(e.mape) AS mape,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY e.mape) AS mape_median,
       avg(e.dir_acc) AS dir_acc,
       avg(CASE WHEN e.mape IS NULL OR b.mape IS NULL THEN NULL
                WHEN e.mape < b.mape THEN 1.0 ELSE 0.0 END) AS beats_naive
FROM e
LEFT JOIN e b ON b.code = e.code AND b.horizon = e.horizon AND b.model = 'naive'
GROUP BY e.as_of, e.model, e.horizon
ORDER BY e.horizon, e.model
"""
)


def _r(v, nd=4):
    return None if v is None else round(float(v), nd)


@router.get(
    "/backtest/summary", response_model=BacktestSummary, responses={401: {"description": "Giriş gerekli"}}
)
def backtest_summary(
    window_days: int = Query(60, ge=1, le=1000),
    type: Literal["stock", "fund", "index"] | None = None,  # noqa: A002 — sözleşmedeki ad
    db: Session = Depends(get_db),
):
    rows = db.execute(_SQL, {"w": window_days, "t": type}).all()
    return BacktestSummary(
        as_of=rows[0].as_of if rows else None,
        window_days=window_days,
        asset_type=type,
        metrics=[
            ModelMetric(
                model=r.model,
                horizon=r.horizon,
                is_baseline=r.model in BASELINES,
                n_assets=r.n_assets,
                mape=_r(r.mape),
                mape_median=_r(r.mape_median),
                dir_acc=_r(r.dir_acc),
                beats_naive=None if r.model == "naive" else _r(r.beats_naive),
            )
            for r in rows
        ],
    )
