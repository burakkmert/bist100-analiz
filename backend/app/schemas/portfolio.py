"""Portföy, izleme listesi ve cihaz şemaları (shared/openapi.yaml ile birebir)."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class PositionCreate(BaseModel):
    """ "Aldım" kaydı. Uygulama işlem yapmaz; kullanıcı kendi aldığını kaydeder."""

    code: str = Field(min_length=1, max_length=16, examples=["THYAO"])
    qty: float = Field(gt=0, examples=[10])
    buy_price: float = Field(gt=0, examples=[312.5])
    buy_date: date = Field(examples=["2026-10-07"])
    signal_id: int | None = Field(default=None, description="Bu kayıt bir model sinyalinden geldiyse")


class PositionSell(BaseModel):
    """ "Sattım" kaydı."""

    sell_price: float = Field(gt=0, examples=[330.0])
    sell_date: date = Field(examples=["2026-10-12"])


class Position(PositionCreate):
    id: int
    sell_price: float | None = None
    sell_date: date | None = None
    # Sözleşmeye ek (opsiyonel) alanlar: sunucu tarafı kâr/zarar.
    # Açık pozisyonda son kapanış fiyatıyla, kapalıda satış fiyatıyla hesaplanır.
    last_price: float | None = Field(default=None, description="Açıkta son kapanış, kapalıda satış fiyatı")
    pnl: float | None = Field(default=None, description="TL kâr/zarar")
    pnl_pct: float | None = Field(default=None, description="Yüzde kâr/zarar")


class WatchlistAdd(BaseModel):
    code: str = Field(min_length=1, max_length=16, examples=["THYAO"])


class PushTokenIn(BaseModel):
    token: str = Field(min_length=1, max_length=512, examples=["ExponentPushToken[xxxx]"])
    platform: Literal["ios", "android"]
