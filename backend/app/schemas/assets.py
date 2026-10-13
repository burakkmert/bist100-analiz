"""Piyasa verisi uçlarının yanıt şemaları (shared/openapi.yaml v0.2 ile birebir)."""

from datetime import date
from typing import Literal

from pydantic import BaseModel

AssetType = Literal["stock", "fund", "index"]


class AssetListItem(BaseModel):
    code: str
    name: str
    type: AssetType
    sector: str | None = None
    last_price: float
    change_pct: float | None  # tek günlük veri varsa hesaplanamaz


class PricePoint(BaseModel):
    date: date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float
    adj_close: float | None = None
    volume: int | None = None


class ForecastBand(BaseModel):
    model: str
    horizon: int
    p10: float
    p50: float | None  # 120 günde nokta tahmin yok
    p90: float


class Scenario(BaseModel):
    horizon: int
    bear: float
    base: float
    bull: float


class Forecast(BaseModel):
    code: str
    run_date: date
    bands: list[ForecastBand]
    scenarios: list[Scenario]


class Range(BaseModel):
    low: float | None
    mid: float | None
    high: float | None


class Analysis(BaseModel):
    code: str
    run_date: date
    horizon: int
    range: Range
    direction: str | None
    confidence: int | None
    risk: str | None
    regime: str | None
    weights: dict | None
    indicators: dict | None
    comment: str | None
