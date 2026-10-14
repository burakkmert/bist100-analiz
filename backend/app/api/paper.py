"""Sanal portföy (Aşama 2): GET /paper-portfolio.

"Alım yönlü model sinyallerine otomatik uyulsaydı ne olurdu?" Ayrı bir tablo tutulmaz (şema değişmez):
sinyaller, sonuçları (outcome) ve fiyatlar gece işleriyle güncellendiği için portföy her istekte bu
verilerden hesaplanır — yani her gece kendiliğinden güncel olur.

Kurallar
  * Her alım yönlü sinyal bir sanal pozisyon açar: giriş = sinyal günündeki kapanış,
    adet = sinyalin önerdiği adet (öneri yoksa 1).
  * Ufuk dolunca (outcome dolu) pozisyon gerçekleşen fiyattan kapanır — sinyal siciliyle aynı kural.
  * Ufku dolmamış pozisyon son kapanışla değerlenir.
Satış yönlü sinyaller kullanıcının GERÇEK pozisyonlarına ilişkin olduğundan sanal portföye girmez.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, get_current_user
from app.core.db import get_db
from app.schemas.paper import PaperPortfolio, PaperPosition, PaperSummary

router = APIRouter(tags=["signals"])

_SQL = text(
    """
    SELECT s.id, s.code, s.horizon, s.confidence, s.suggested_qty, s.created_at, s.outcome,
           e.close AS entry_close, l.close AS last_close
    FROM signals s
    LEFT JOIN LATERAL (
        SELECT close FROM prices
        WHERE code = s.code AND date <= (s.created_at AT TIME ZONE 'Europe/Istanbul')::date
        ORDER BY date DESC LIMIT 1
    ) e ON true
    LEFT JOIN LATERAL (SELECT close FROM prices WHERE code = s.code ORDER BY date DESC LIMIT 1) l ON true
    WHERE s.user_id = CAST(:u AS uuid) AND s.side = 'buy'
    ORDER BY s.created_at DESC, s.id DESC
    """
)


def _f(v) -> float | None:
    return None if v is None else float(v)


def build(rows) -> PaperPortfolio:
    positions: list[PaperPosition] = []
    for r in rows:
        out = r.outcome or None
        qty = _f(r.suggested_qty) or 1.0
        entry = _f(out.get("entry")) if out and out.get("entry") is not None else _f(r.entry_close)
        closed = out is not None and out.get("realized") is not None
        exit_ = _f(out["realized"]) if closed else None
        price = exit_ if closed else _f(r.last_close)
        pnl = pnl_pct = None
        if entry and price is not None:
            pnl = round((price - entry) * qty, 2)
            pnl_pct = round((price / entry - 1) * 100, 2)
        positions.append(
            PaperPosition(
                signal_id=r.id,
                code=r.code,
                horizon=r.horizon,
                confidence=r.confidence,
                opened_at=r.created_at,
                qty=qty,
                entry=entry,
                exit=exit_,
                last_price=None if closed else price,
                closed=closed,
                closed_on=date.fromisoformat(out["evaluated_on"])
                if closed and out.get("evaluated_on")
                else None,
                pnl=pnl,
                pnl_pct=pnl_pct,
            )
        )
    valued = [p for p in positions if p.entry and p.pnl is not None]
    invested = round(sum(p.entry * p.qty for p in valued), 2)
    pnl = round(sum(p.pnl for p in valued), 2)
    closed = [p for p in positions if p.closed]
    wins = [p for p in closed if p.pnl is not None and p.pnl > 0]
    summary = PaperSummary(
        positions=len(positions),
        open=len(positions) - len(closed),
        closed=len(closed),
        invested=invested,
        value=round(invested + pnl, 2),
        pnl=pnl,
        pnl_pct=round(pnl / invested * 100, 2) if invested else None,
        hit_rate=round(len(wins) / len(closed), 4) if closed else None,
    )
    return PaperPortfolio(summary=summary, positions=positions)


@router.get(
    "/paper-portfolio", response_model=PaperPortfolio, responses={401: {"description": "Giriş gerekli"}}
)
def paper_portfolio(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return build(db.execute(_SQL, {"u": str(user.id)}).all())
