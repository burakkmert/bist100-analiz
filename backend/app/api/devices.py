"""POST /devices/push-token — Expo push token kaydı.

Aynı token başka bir kullanıcıya kayıtlıysa (cihazda hesap değiştirildi) eski kayıt silinir:
bir cihaz yalnızca son giriş yapan kullanıcının bildirimlerini almalı.
"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, get_current_user
from app.core.db import get_db
from app.models import PushToken
from app.schemas.portfolio import PushTokenIn

router = APIRouter(tags=["signals"])


@router.post(
    "/devices/push-token",
    status_code=204,
    response_class=Response,
    responses={401: {"description": "Giriş gerekli"}},
)
def register_push_token(
    body: PushTokenIn, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
):
    db.execute(delete(PushToken).where(PushToken.token == body.token, PushToken.user_id != user.id))
    stmt = insert(PushToken).values(user_id=user.id, token=body.token, platform=body.platform)
    db.execute(
        stmt.on_conflict_do_update(index_elements=["user_id", "token"], set_={"platform": body.platform})
    )
    db.commit()
    return Response(status_code=204)
