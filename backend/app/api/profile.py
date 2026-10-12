"""GET/PUT /me/profile — kullanıcının risk profili, bütçesi ve bildirim ayarları."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, get_current_user
from app.core.db import get_db
from app.models import Profile
from app.schemas.profile import ProfileOut, ProfileUpdate

router = APIRouter(prefix="/me", tags=["profile"])

UNAUTHORIZED = {401: {"description": "Giriş yok veya token geçersiz"}}


def _to_out(p: Profile, email: str) -> ProfileOut:
    return ProfileOut(
        email=email,
        risk_profile=p.risk_profile,
        budget=float(p.budget) if p.budget is not None else None,
        quiet_hours=p.quiet_hours,
        daily_push_limit=p.daily_push_limit,
    )


def _get_profile(db: Session, user: CurrentUser) -> Profile:
    profile = db.get(Profile, user.id)
    if profile is None:  # get_current_user oluşturur; buraya düşmemeli
        raise HTTPException(500, "Profil bulunamadı")
    return profile


@router.get("/profile", response_model=ProfileOut, responses=UNAUTHORIZED)
def get_profile(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return _to_out(_get_profile(db, user), user.email)


@router.put("/profile", response_model=ProfileOut, responses={**UNAUTHORIZED, 422: {}})
def update_profile(
    body: ProfileUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(db, user)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    db.commit()
    db.refresh(profile)
    return _to_out(profile, user.email)
