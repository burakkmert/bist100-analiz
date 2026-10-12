"""Supabase JWT doğrulama.

Mobil uygulama Supabase ile giriş yapar ve aldığı access token'ı her istekte
`Authorization: Bearer <token>` başlığıyla gönderir. Burada token'ı doğrular,
kullanıcıyı `users` tablosunda yoksa oluştururuz (ilk girişte otomatik kayıt).

İki doğrulama yolu desteklenir:
- HS256: SUPABASE_JWT_SECRET (klasik Supabase projeleri)
- ES256/RS256: Supabase JWKS uç noktası (yeni asimetrik anahtarlı projeler)

Kişi 3'ün /ai router'ı da aynı `get_current_user` bağımlılığını kullanır.
"""

import uuid
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.models import Profile, User

bearer = HTTPBearer(auto_error=False)

DEV_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
DEV_USER_EMAIL = "dev@fontakip.local"


@dataclass(frozen=True)
class CurrentUser:
    id: uuid.UUID
    email: str


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True)


def decode_token(token: str, settings: Settings) -> dict:
    """Token'ı doğrular ve içeriğini (claims) döner. Geçersizse HTTP 401."""
    try:
        alg = jwt.get_unverified_header(token).get("alg")
        if alg == "HS256":
            if not settings.supabase_jwt_secret:
                raise jwt.InvalidTokenError("SUPABASE_JWT_SECRET tanımlı değil")
            key = settings.supabase_jwt_secret
        elif alg in ("ES256", "RS256"):
            if not settings.jwks_url:
                raise jwt.InvalidTokenError("JWKS adresi tanımlı değil")
            key = _jwks_client(settings.jwks_url).get_signing_key_from_jwt(token).key
        else:
            raise jwt.InvalidTokenError(f"Desteklenmeyen algoritma: {alg}")

        return jwt.decode(
            token,
            key,
            algorithms=[alg],
            audience=settings.supabase_jwt_audience,
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise _unauthorized("Geçersiz veya süresi dolmuş oturum") from exc


def _ensure_user(db: Session, user_id: uuid.UUID, email: str) -> None:
    """İlk girişte kullanıcı + varsayılan profil oluştur; e-posta değiştiyse güncelle."""
    stmt = insert(User).values(id=user_id, email=email)
    db.execute(stmt.on_conflict_do_update(index_elements=["id"], set_={"email": stmt.excluded.email}))
    db.execute(insert(Profile).values(user_id=user_id).on_conflict_do_nothing())
    db.commit()


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    if creds is None:
        if settings.auth_dev_bypass and settings.app_env == "dev":
            _ensure_user(db, DEV_USER_ID, DEV_USER_EMAIL)
            return CurrentUser(id=DEV_USER_ID, email=DEV_USER_EMAIL)
        raise _unauthorized("Giriş gerekli")

    claims = decode_token(creds.credentials, settings)
    try:
        user_id = uuid.UUID(claims["sub"])
    except ValueError as exc:
        raise _unauthorized("Geçersiz kullanıcı kimliği") from exc
    # Telefonla/anonim girişte e-posta olmayabilir; users.email NOT NULL + UNIQUE
    email = claims.get("email") or f"{user_id}@no-email.local"

    _ensure_user(db, user_id, email)
    return CurrentUser(id=user_id, email=email)
