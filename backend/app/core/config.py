"""Uygulama ayarları. Değerler ortam değişkenlerinden / .env dosyasından okunur.

Okuma sırası: ortam değişkeni > backend/.env > repo kökündeki .env
(Kişi 3'ün LLM anahtarları backend/.env'de durabilir.)
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILES = (BACKEND_DIR.parent / ".env", BACKEND_DIR / ".env")  # sonraki öncekini ezer


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILES, extra="ignore")

    app_env: str = "dev"
    database_url: str = "postgresql+psycopg://fon:fon@localhost:5432/fontakip"
    mock: bool = False
    cors_origins: str = "*"

    supabase_url: str = ""
    supabase_jwt_secret: str = ""
    supabase_jwks_url: str = ""
    # Supabase, giriş yapmış kullanıcı tokenlarında aud="authenticated" kullanır
    supabase_jwt_audience: str = "authenticated"

    # Yalnızca geliştirme: 1 ise token olmayan istekler sabit bir "dev" kullanıcısı sayılır.
    # Supabase girişi mobilde hazır olana kadar ekip uygulamayı deneyebilsin diye. Üretimde 0.
    auth_dev_bypass: bool = False

    expo_access_token: str = ""

    # İstek sınırı (dakikada, kullanıcı başına). 0 = kapalı. Ayrıntı: app/core/ratelimit.py
    rate_limit_per_min: int = 120
    rate_limit_ai_per_min: int = 10

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def jwks_url(self) -> str:
        if self.supabase_jwks_url:
            return self.supabase_jwks_url
        if self.supabase_url:
            return self.supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json"
        return ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
