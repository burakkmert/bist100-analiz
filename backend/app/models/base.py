"""Tüm SQLAlchemy modellerinin ortak tabanı ve tekrar eden sütun tipleri."""

from sqlalchemy import Numeric, String
from sqlalchemy.orm import DeclarativeBase

# shared/db_schema.sql ile aynı tipler
Code = String(16)
Price = Numeric(18, 6)
Qty = Numeric(18, 4)
Money = Numeric(18, 2)


class Base(DeclarativeBase):
    pass
