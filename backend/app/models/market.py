"""Kişi 1'in yazdığı veri tabloları (shared/db_schema.sql). Backend bunları yalnızca OKUR."""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Double,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Code, Price


class Asset(Base):
    __tablename__ = "assets"

    code: Mapped[str] = mapped_column(Code, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(8))  # 'stock' | 'fund' | 'index' (XU100; tahmin/sinyal yok)
    sector: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    min_history_ok: Mapped[bool] = mapped_column(Boolean, server_default="false")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PriceBar(Base):
    """Günlük fiyat çubuğu (OHLCV). Fonlarda yalnızca close doludur."""

    __tablename__ = "prices"

    code: Mapped[str] = mapped_column(Code, ForeignKey("assets.code"), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[float | None] = mapped_column(Price)
    high: Mapped[float | None] = mapped_column(Price)
    low: Mapped[float | None] = mapped_column(Price)
    close: Mapped[float] = mapped_column(Price)
    adj_close: Mapped[float | None] = mapped_column(Price)
    volume: Mapped[int | None] = mapped_column(BigInteger)


class Forecast(Base):
    __tablename__ = "forecasts"

    code: Mapped[str] = mapped_column(Code, ForeignKey("assets.code"), primary_key=True)
    run_date: Mapped[date] = mapped_column(Date, primary_key=True)
    model: Mapped[str] = mapped_column(String(32), primary_key=True)
    horizon: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    p10: Mapped[float | None] = mapped_column(Price)
    p50: Mapped[float | None] = mapped_column(Price)  # 120 günde NULL
    p90: Mapped[float | None] = mapped_column(Price)


class Scenario(Base):
    __tablename__ = "scenarios"

    code: Mapped[str] = mapped_column(Code, ForeignKey("assets.code"), primary_key=True)
    run_date: Mapped[date] = mapped_column(Date, primary_key=True)
    horizon: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    bear: Mapped[float | None] = mapped_column(Price)
    base: Mapped[float | None] = mapped_column(Price)
    bull: Mapped[float | None] = mapped_column(Price)


class ModelError(Base):
    __tablename__ = "model_errors"

    code: Mapped[str] = mapped_column(Code, ForeignKey("assets.code"), primary_key=True)
    model: Mapped[str] = mapped_column(String(32), primary_key=True)
    horizon: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    window_days: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    mae: Mapped[float | None] = mapped_column(Double)
    mape: Mapped[float | None] = mapped_column(Double)
    dir_acc: Mapped[float | None] = mapped_column(Double)
    as_of: Mapped[date] = mapped_column(Date, primary_key=True)
