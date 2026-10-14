"""Sinyal uçları (Görev 7): /signals, /signals/track-record.

Sinyalleri gece engine.run_signals üretir; bu uçlar yalnızca OKUR ve her sorgu user_id ile süzülür.
"Sinyal sicili" modelin geçmiş isabetini şeffaf gösterir (ufku dolan sinyallerin outcome'u).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, get_current_user
from app.core.db import get_db
from app.models import Signal as SignalRow
from app.schemas.signals import RecordBucket, Signal, TrackRecord

router = APIRouter(tags=["signals"])

UNAUTHORIZED = {401: {"description": "Giriş yok veya token geçersiz"}}


@router.get("/signals", response_model=list[Signal], responses=UNAUTHORIZED)
def list_signals(
    status: Literal["open", "closed"] | None = None,
    limit: int = Query(100, ge=1, le=500),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """open → ufku dolmamış (outcome yok), closed → sonuçlanmış, boş → hepsi. Yeniden eskiye."""
    q = select(SignalRow).where(SignalRow.user_id == user.id)
    if status == "open":
        q = q.where(SignalRow.outcome.is_(None))
    elif status == "closed":
        q = q.where(SignalRow.outcome.is_not(None))
    rows = db.scalars(q.order_by(SignalRow.created_at.desc(), SignalRow.id.desc()).limit(limit)).all()
    return [
        Signal(
            id=r.id,
            code=r.code,
            side=r.side,
            horizon=r.horizon,
            confidence=r.confidence or 0,
            suggested_qty=None if r.suggested_qty is None else float(r.suggested_qty),
            stop_level=None if r.stop_level is None else float(r.stop_level),
            created_at=r.created_at,
            outcome=r.outcome,
        )
        for r in rows
    ]


# Sonuçlanmış sinyallerin özeti: GROUPING SETS ile genel + yön + ufuk kırılımları tek sorguda.
# :u NULL ise tüm kullanıcılar; aynı (varlık, yön, ufuk, gece) birden çok kullanıcıya
# gittiyse bir kez sayılır.
_RECORD_SQL = text(
    """
WITH s AS (
    SELECT DISTINCT ON (code, side, horizon, created_at,
                        CASE WHEN CAST(:u AS uuid) IS NULL THEN NULL ELSE id END)
           side, horizon,
           (outcome->>'hit')::boolean AS hit,
           CASE WHEN side = 'buy' THEN 1 ELSE -1 END * (outcome->>'return_pct')::float AS ret
    FROM signals
    WHERE outcome IS NOT NULL AND (CAST(:u AS uuid) IS NULL OR user_id = CAST(:u AS uuid))
)
SELECT side, horizon, GROUPING(side) AS g_side, GROUPING(horizon) AS g_h,
       count(*) AS closed, count(*) FILTER (WHERE hit) AS hits, avg(ret) AS avg_ret
FROM s
GROUP BY GROUPING SETS ((), (side), (horizon))
ORDER BY g_side DESC, g_h DESC, side, horizon
"""
)


def _record(db: Session, user_id) -> tuple[RecordBucket, list[RecordBucket]]:
    total = RecordBucket(closed=0, hits=0, hit_rate=None, avg_return_pct=None)
    parts = []
    for r in db.execute(_RECORD_SQL, {"u": None if user_id is None else str(user_id)}):
        b = RecordBucket(
            side=None if r.g_side else r.side,
            horizon=None if r.g_h else r.horizon,
            closed=r.closed,
            hits=r.hits,
            hit_rate=round(r.hits / r.closed, 4) if r.closed else None,
            avg_return_pct=None if r.avg_ret is None else round(float(r.avg_ret), 4),
        )
        if r.g_side and r.g_h:
            total = b
        else:
            parts.append(b)
    return total, parts


@router.get("/signals/track-record", response_model=TrackRecord, responses=UNAUTHORIZED)
def track_record(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Sinyal sicili: kullanıcının ve modelin (tüm kullanıcılar) geçmiş isabeti.
    İsabet: alım yönlüde ufuk sonunda fiyat girişin üstünde, satış yönlüde altında."""
    n_open = db.scalar(select(func.count()).where(SignalRow.user_id == user.id, SignalRow.outcome.is_(None)))
    mine, mine_by = _record(db, user.id)
    model, model_by = _record(db, None)
    return TrackRecord(open=n_open or 0, mine=mine, mine_by=mine_by, model=model, model_by=model_by)
