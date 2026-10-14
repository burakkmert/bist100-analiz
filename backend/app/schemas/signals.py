"""Sinyal şemaları (shared/openapi.yaml 'Signal'). side=buy/sell arayüzde
"alım/satış yönlü model sinyali" olarak gösterilir — yatırım tavsiyesi değildir (SPK)."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class SignalOutcome(BaseModel):
    realized: float
    hit: bool
    # Sözleşmeye ek (opsiyonel): giriş fiyatı, getiri ve değerlendirme günü
    entry: float | None = None
    return_pct: float | None = None
    evaluated_on: date | None = None


class Signal(BaseModel):
    id: int
    code: str
    side: Literal["buy", "sell"]
    horizon: int
    confidence: int = Field(ge=0, le=100)
    suggested_qty: float | None = None
    stop_level: float | None = None
    created_at: datetime
    outcome: SignalOutcome | None = None


class RecordBucket(BaseModel):
    """Sonuçlanmış sinyallerin özeti. avg_return_pct sinyal yönünde ölçülür:
    satış yönlü sinyalde fiyat düştüyse pozitif."""

    side: Literal["buy", "sell"] | None = None
    horizon: int | None = None
    closed: int
    hits: int
    hit_rate: float | None
    avg_return_pct: float | None


class TrackRecord(BaseModel):
    open: int = Field(description="Ufku henüz dolmamış sinyaller (kullanıcının)")
    mine: RecordBucket = Field(description="Kullanıcının kendi sinyalleri")
    mine_by: list[RecordBucket]
    model: RecordBucket = Field(description="Tüm kullanıcılar; aynı gece-varlık-yön-ufuk bir kez sayılır")
    model_by: list[RecordBucket]


class Band(BaseModel):
    low: float | None
    mid: float | None
    high: float | None


class SignalExplanation(BaseModel):
    """ "Bu sinyal neden?" (Aşama 2): sinyalin üretildiği gecenin karar motoru çıktısı, bileşenleriyle."""

    signal: Signal
    run_date: date = Field(description="Sinyalin dayandığı analiz gecesi")
    direction: str
    confidence: int | None
    risk: str | None
    regime: str | None
    market_regime: str | None = Field(description="BIST 100 rejimi")
    weights: dict | None = Field(description="Model ağırlıkları (∝ 1/MAE)")
    confidence_parts: dict | None = Field(description="Güven skorunun bileşenleri: temel, güç, uyum, cezalar")
    indicators: dict | None = Field(description="O geceki gösterge değerleri (RSI, MACD, MA, ATR, vol20…)")
    calibration: dict | None = Field(description="Geçmiş isabet (varsa)")
    band: Band = Field(description="Ensemble tahmin bandı p10 / p50 / p90")
    comment: str | None = Field(description="Yapay zekâ yorumu (varsa)")
    disclaimer: str = "Model sinyalidir, yatırım tavsiyesi değildir."
