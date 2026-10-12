from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db

router = APIRouter(tags=["system"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    """Sunucu ve veritabanı ayakta mı? (Docker ve demo için)"""
    db.execute(text("SELECT 1"))
    return {"status": "ok", "db": "ok", "mock": get_settings().mock}
