"""Karar motorunun (Kişi 2) ve yapay zekâ katmanının (Kişi 3) çıktı tabloları."""

from datetime import date

from sqlalchemy import Date, ForeignKey, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Code, Price


class Analysis(Base):
    __tablename__ = "analysis"

    code: Mapped[str] = mapped_column(Code, ForeignKey("assets.code"), primary_key=True)
    run_date: Mapped[date] = mapped_column(Date, primary_key=True)
    horizon: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    direction: Mapped[str | None] = mapped_column(String(4))  # up | down | flat
    confidence: Mapped[int | None] = mapped_column(SmallInteger)  # 0–100
    risk: Mapped[str | None] = mapped_column(String(8))  # low | medium | high
    regime: Mapped[str | None] = mapped_column(String(16))  # trend | range | high_vol
    weights: Mapped[dict | None] = mapped_column(JSONB)  # ilk günden doldurulur
    indicators: Mapped[dict | None] = mapped_column(JSONB)  # ilk günden doldurulur
    low: Mapped[float | None] = mapped_column(Price)
    mid: Mapped[float | None] = mapped_column(Price)
    high: Mapped[float | None] = mapped_column(Price)


class AiExplanation(Base):
    """Kişi 3 yazar; backend /analysis yanıtına 'comment' olarak ekler."""

    __tablename__ = "ai_explanations"

    code: Mapped[str] = mapped_column(Code, ForeignKey("assets.code"), primary_key=True)
    run_date: Mapped[date] = mapped_column(Date, primary_key=True)
    horizon: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
