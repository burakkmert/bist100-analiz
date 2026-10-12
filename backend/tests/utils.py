"""Testlerde kullanılan yardımcılar (Supabase benzeri token üretimi)."""

import time
import uuid

import jwt

TEST_JWT_SECRET = "test-secret-en-az-32-karakter-uzunlugunda!!"


def make_token(
    user_id: uuid.UUID | None = None,
    email: str = "test@example.com",
    *,
    exp_in: int = 3600,
    audience: str = "authenticated",
    secret: str = TEST_JWT_SECRET,
) -> str:
    """Supabase'in ürettiğine benzer bir HS256 access token üretir."""
    now = int(time.time())
    payload = {
        "sub": str(user_id or uuid.uuid4()),
        "email": email,
        "aud": audience,
        "role": "authenticated",
        "iat": now,
        "exp": now + exp_in,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
