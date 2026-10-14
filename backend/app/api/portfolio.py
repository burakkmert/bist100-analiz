"""Portföy ve izleme listesi (Görev 4): /portfolio, /watchlist.

Güvenlik kuralı: HER sorgu user_id ile süzülür. Başka kullanıcının kaydı "yok" sayılır (404),
varlığı bile sızdırılmaz. Uygulama işlem yapmaz; kullanıcı kendi aldığını/sattığını kaydeder.

Bu uçlar piyasa verisine bağlı değildir; MOCK=1 iken de gerçek veritabanıyla çalışır.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, get_current_user
from app.core.clock import today_tr
from app.core.db import get_db
from app.models import Asset, Position, Signal, Watchlist
from app.schemas.portfolio import Position as PositionOut
from app.schemas.portfolio import PositionCreate, PositionSell, WatchlistAdd

router = APIRouter(tags=["portfolio"])

UNAUTHORIZED = {401: {"description": "Giriş yok veya token geçersiz"}}
NOT_FOUND = {404: {"description": "Bulunamadı"}, **UNAUTHORIZED}

_LAST_CLOSE_SQL = text(
    "SELECT DISTINCT ON (code) code, close FROM prices "
    "WHERE code = ANY(CAST(:codes AS text[])) ORDER BY code, date DESC"
)


def _code(raw: str) -> str:
    return raw.strip().upper()


def _require_asset(db: Session, code: str) -> None:
    if db.get(Asset, code) is None:
        raise HTTPException(422, f"Bilinmeyen varlık kodu: {code}")


def _not_future(d, field: str) -> None:
    if d > today_tr():
        raise HTTPException(422, f"{field} gelecekte olamaz")


def _last_closes(db: Session, codes: set[str]) -> dict[str, float]:
    if not codes:
        return {}
    return {r.code: float(r.close) for r in db.execute(_LAST_CLOSE_SQL, {"codes": sorted(codes)})}


def _to_out(p: Position, last: dict[str, float]) -> PositionOut:
    qty, buy = float(p.qty), float(p.buy_price)
    price = float(p.sell_price) if p.sell_price is not None else last.get(p.code)
    pnl = pnl_pct = None
    if price is not None:
        pnl = round((price - buy) * qty, 2)
        pnl_pct = round((price / buy - 1) * 100, 2)
    return PositionOut(
        id=p.id,
        code=p.code,
        qty=qty,
        buy_price=buy,
        buy_date=p.buy_date,
        signal_id=p.signal_id,
        sell_price=float(p.sell_price) if p.sell_price is not None else None,
        sell_date=p.sell_date,
        last_price=price,
        pnl=pnl,
        pnl_pct=pnl_pct,
    )


def _own_position(db: Session, user: CurrentUser, position_id: int) -> Position:
    p = db.scalar(select(Position).where(Position.id == position_id, Position.user_id == user.id))
    if p is None:
        raise HTTPException(404, "Kayıt bulunamadı")
    return p


# --------------------------------------------------------------------------- /portfolio


@router.get("/portfolio", response_model=list[PositionOut], responses=UNAUTHORIZED)
def list_positions(
    status: Literal["open", "closed"] | None = None,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Kullanıcının pozisyonları. status=open → satılmamış, closed → satılmış, boş → hepsi.
    Kâr/zarar açıkta son kapanışla, kapalıda satış fiyatıyla hesaplanır."""
    q = select(Position).where(Position.user_id == user.id)
    if status == "open":
        q = q.where(Position.sell_date.is_(None))
    elif status == "closed":
        q = q.where(Position.sell_date.is_not(None))
    rows = db.scalars(q.order_by(Position.buy_date.desc(), Position.id.desc())).all()
    last = _last_closes(db, {p.code for p in rows if p.sell_price is None})
    return [_to_out(p, last) for p in rows]


@router.post(
    "/portfolio",
    response_model=PositionOut,
    status_code=201,
    responses={**UNAUTHORIZED, 422: {"description": "Doğrulama hatası (ör. gelecek tarih, qty ≤ 0)"}},
)
def create_position(
    body: PositionCreate,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    code = _code(body.code)
    _require_asset(db, code)
    _not_future(body.buy_date, "Alış tarihi")
    if body.signal_id is not None:
        sig = db.scalar(select(Signal).where(Signal.id == body.signal_id, Signal.user_id == user.id))
        if sig is None or sig.code != code:
            raise HTTPException(422, "signal_id bu kullanıcıya ve bu varlığa ait bir sinyal değil")
    p = Position(
        user_id=user.id,
        code=code,
        qty=body.qty,
        buy_price=body.buy_price,
        buy_date=body.buy_date,
        signal_id=body.signal_id,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return _to_out(p, _last_closes(db, {code}))


@router.patch(
    "/portfolio/{id}",
    response_model=PositionOut,
    responses={**NOT_FOUND, 422: {"description": "Satış tarihi alıştan önce olamaz"}},
)
def sell_position(
    id: int,  # noqa: A002 — sözleşmedeki yol parametresi adı
    body: PositionSell,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """ "Sattım" kaydı. Tekrar çağrılırsa satış bilgisi düzeltilir."""
    p = _own_position(db, user, id)
    if body.sell_date < p.buy_date:
        raise HTTPException(422, "Satış tarihi alıştan önce olamaz")
    _not_future(body.sell_date, "Satış tarihi")
    p.sell_price, p.sell_date = body.sell_price, body.sell_date
    db.commit()
    db.refresh(p)
    return _to_out(p, {})


@router.delete("/portfolio/{id}", status_code=204, response_class=Response, responses=NOT_FOUND)
def delete_position(
    id: int,  # noqa: A002 — sözleşmedeki yol parametresi adı
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.delete(_own_position(db, user, id))
    db.commit()
    return Response(status_code=204)


# --------------------------------------------------------------------------- /watchlist


@router.get("/watchlist", response_model=list[str], responses=UNAUTHORIZED)
def get_watchlist(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return list(
        db.scalars(select(Watchlist.code).where(Watchlist.user_id == user.id).order_by(Watchlist.code))
    )


@router.post(
    "/watchlist",
    status_code=204,
    response_class=Response,
    responses={**UNAUTHORIZED, 422: {"description": "Bilinmeyen varlık kodu"}},
)
def add_watchlist(
    body: WatchlistAdd, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Zaten listedeyse de 204 (idempotent)."""
    code = _code(body.code)
    _require_asset(db, code)
    db.execute(insert(Watchlist).values(user_id=user.id, code=code).on_conflict_do_nothing())
    db.commit()
    return Response(status_code=204)


@router.delete("/watchlist/{code}", status_code=204, response_class=Response, responses=UNAUTHORIZED)
def remove_watchlist(code: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Listede yoksa da 204 (idempotent)."""
    db.query(Watchlist).filter(Watchlist.user_id == user.id, Watchlist.code == _code(code)).delete()
    db.commit()
    return Response(status_code=204)
