"""Ayarlar: bulut sağlayıcılarının bağlantı metni psycopg (3) sürücüsüne çevrilir."""

import pytest

from app.core.config import Settings
from engine.run_engine import db_url


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("postgresql://u:p%40x@h:5432/db", "postgresql+psycopg://u:p%40x@h:5432/db"),
        ("postgres://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
    ],
)
def test_baglanti_metni_surucusu(raw, expected):
    assert Settings(database_url=raw).database_url == expected
    assert db_url(raw) == expected
