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
