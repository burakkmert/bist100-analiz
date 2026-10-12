"""Test ortamı.

Testler gerçek bir PostgreSQL ister (JSONB, UUID, ON CONFLICT kullanıyoruz).
- Yerelde:  docker compose up -d db  →  cd backend && pytest
- CI'da:    GitHub Actions postgres servisi (ci.yml)
TEST_DATABASE_URL verilmezse yerel docker DB'sindeki "fontakip_test" kullanılır.
"""

import os

import pytest

TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://fon:fon@localhost:5432/fontakip_test")
from tests.utils import TEST_JWT_SECRET  # noqa: E402

# Ayarlar önbelleğe alınmadan ÖNCE ortamı belirle
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["SUPABASE_JWT_SECRET"] = TEST_JWT_SECRET
os.environ["MOCK"] = "0"
os.environ["AUTH_DEV_BYPASS"] = "0"
os.environ["APP_ENV"] = "test"

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ensure_database(url: str) -> None:
    """Test veritabanı yoksa oluşturur."""
    u = make_url(url)
    admin = create_engine(u.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": u.database})
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{u.database}"'))
    admin.dispose()


def _reset_schema(url: str) -> None:
    eng = create_engine(url)
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    eng.dispose()


def alembic_upgrade(url: str) -> None:
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    cfg.cmd_opts = type("o", (), {"x": [f"url={url}"]})()
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session", autouse=True)
def database():
    """Oturum başında temiz şema + tüm göçler."""
    _ensure_database(TEST_DB_URL)
    _reset_schema(TEST_DB_URL)
    alembic_upgrade(TEST_DB_URL)
    yield TEST_DB_URL


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)
