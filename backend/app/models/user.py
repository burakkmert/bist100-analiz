"""Kullanıcıya ait tablolar (Kişi 2). Her sorgu user_id ile filtrelenmelidir."""

import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Code, Money, Price, Qty


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)  # Supabase "sub"
    email: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Profile(Base):
    __tablename__ = "profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    risk_profile: Mapped[str] = mapped_column(String(12), server_default="balanced")
    budget: Mapped[float | None] = mapped_column(Money)
    quiet_hours: Mapped[dict | None] = mapped_column(JSONB)  # {"start": "22:30", "end": "08:00"}
    daily_push_limit: Mapped[int | None] = mapped_column(SmallInteger, server_default="5")


class Watchlist(Base):
    __tablename__ = "watchlist"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    code: Mapped[str] = mapped_column(Code, ForeignKey("assets.code"), primary_key=True)


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(Code, ForeignKey("assets.code"))
    side: Mapped[str] = mapped_column(String(4))  # buy | sell
    horizon: Mapped[int] = mapped_column(SmallInteger)  # 1, 5, 20, 30 (120 sinyal üretmez)
    confidence: Mapped[int | None] = mapped_column(SmallInteger)
    suggested_qty: Mapped[float | None] = mapped_column(Qty)
    stop_level: Mapped[float | None] = mapped_column(Price)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    outcome: Mapped[dict | None] = mapped_column(JSONB)  # {"realized": .., "hit": true}


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(Code, ForeignKey("assets.code"))
    qty: Mapped[float] = mapped_column(Qty)
    buy_price: Mapped[float] = mapped_column(Price)
    buy_date: Mapped[date] = mapped_column(Date)
    sell_price: Mapped[float | None] = mapped_column(Price)
    sell_date: Mapped[date | None] = mapped_column(Date)
    signal_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("signals.id"))


class PushToken(Base):
    __tablename__ = "push_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    token: Mapped[str] = mapped_column(Text, primary_key=True)
    platform: Mapped[str | None] = mapped_column(String(8))  # ios | android
