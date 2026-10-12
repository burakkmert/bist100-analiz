"""Sözleşme testi: SQLAlchemy modelleri, Alembic ile kurulan veritabanı ve
shared/db_schema.sql birbiriyle aynı mı?

Biri modele sütun ekleyip göç yazmayı (veya sözleşmeyi güncellemeyi)
unutursa bu test kırmızı yanar.
"""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from app.models import Base

SCHEMA_SQL = Path(__file__).resolve().parents[2] / "shared" / "db_schema.sql"


def _describe(url: str) -> dict:
    """Her tablo için {sütun: (tip, nullable)} ve birincil anahtar."""
    eng = create_engine(url)
    insp = inspect(eng)
    out = {}
    for table in insp.get_table_names():
        if table == "alembic_version":
            continue
        cols = {c["name"]: (str(c["type"]).upper(), c["nullable"]) for c in insp.get_columns(table)}
        pk = tuple(insp.get_pk_constraint(table)["constrained_columns"])
        out[table] = {"cols": cols, "pk": pk}
    eng.dispose()
    return out


@pytest.fixture(scope="module")
def contract_db(database):
    """shared/db_schema.sql'i ayrı bir şemaya kurar."""
    eng = create_engine(database)
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS contract CASCADE; CREATE SCHEMA contract;"))
        conn.execute(text("SET search_path TO contract"))
        conn.exec_driver_sql(SCHEMA_SQL.read_text(encoding="utf-8"))
    yield eng
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA contract CASCADE"))
    eng.dispose()


def test_alembic_ile_sozlesme_ayni(database, contract_db):
    migrated = _describe(database)
    insp = inspect(contract_db)
    contract = {}
    for table in insp.get_table_names(schema="contract"):
        cols = {
            c["name"]: (str(c["type"]).upper(), c["nullable"])
            for c in insp.get_columns(table, schema="contract")
        }
        pk = tuple(insp.get_pk_constraint(table, schema="contract")["constrained_columns"])
        contract[table] = {"cols": cols, "pk": pk}
    assert migrated == contract


def _constraints(eng, schema: str) -> list[tuple[str, str]]:
    """Tablo + kısıt tanımı (CHECK, PK, FK, UNIQUE). Kısıt adları karşılaştırılmaz."""
    rows = eng.connect().execute(
        text(
            "SELECT c.relname, pg_get_constraintdef(k.oid) FROM pg_constraint k "
            "JOIN pg_class c ON c.oid = k.conrelid JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = :s AND c.relname <> 'alembic_version'"
        ),
        {"s": schema},
    )
    # FK tanımı şema adını içerebilir ("REFERENCES contract.assets"); onu ayıkla
    return sorted((t, d.replace(f"{schema}.", "")) for t, d in rows)


def test_kisitlar_sozlesmeyle_ayni(database, contract_db):
    """Ör. sözleşmede CHECK (type IN ('stock','fund','index')) varsa göçlerde de olmalı."""
    migrated = _constraints(create_engine(database), "public")
    contract = _constraints(contract_db, "contract")
    assert migrated == contract


def test_modeller_ile_veritabani_ayni(database):
    migrated = _describe(database)
    assert set(Base.metadata.tables) == set(migrated), "Tablo listesi farklı"
    for name, table in Base.metadata.tables.items():
        db_cols = migrated[name]["cols"]
        assert set(table.columns.keys()) == set(db_cols), f"{name}: sütunlar farklı"
        for col in table.columns:
            assert col.nullable == db_cols[col.name][1], f"{name}.{col.name}: nullable farklı"
        pk = tuple(c.name for c in table.primary_key.columns)
        assert set(pk) == set(migrated[name]["pk"]), f"{name}: birincil anahtar farklı"
