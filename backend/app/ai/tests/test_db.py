"""Veritabanı kaynakları (app/ai/db.py).

• Satır dönüştürme testi her yerde çalışır.
• Gerçek PostgreSQL testi yalnızca TEST_DATABASE_URL varsa çalışır (CI'da var): shared/db_schema.sql
  ayrı bir şemaya kurulur, örnek satırlar yazılır, okuma ve upsert doğrulanır.
"""
import asyncio
import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.ai.db import analysis_row_to_dict
from app.ai.explain_job import Explanation

SCHEMA_SQL = Path(__file__).resolve().parents[4] / "shared" / "db_schema.sql"
SCHEMA = "ai_db_test"


def test_analysis_satiri_sozlesme_sekline_donusur():
    row = {
        "code": "THYAO", "run_date": date(2026, 10, 13), "horizon": 5, "direction": "up", "confidence": 68,
        "risk": "medium", "regime": "trend", "weights": {"timesfm": 0.6}, "indicators": {"rsi": 58.2},
        "low": Decimal("298.2"), "mid": Decimal("316"), "high": Decimal("333.5"),
    }
    out = analysis_row_to_dict(row)
    assert out["run_date"] == "2026-10-13"
    assert out["range"] == {"low": 298.2, "mid": 316.0, "high": 333.5}
    assert isinstance(out["range"]["low"], float) and out["regime"] == "trend"


@pytest.fixture(scope="module")
def pg():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL yok (yalnızca CI'da / yerel docker DB'siyle çalışır)")
    sa = pytest.importorskip("sqlalchemy")
    from sqlalchemy.orm import sessionmaker

    admin = sa.create_engine(url)
    with admin.begin() as conn:
        conn.execute(sa.text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE; CREATE SCHEMA {SCHEMA};"))
        conn.execute(sa.text(f"SET search_path TO {SCHEMA}"))
        conn.exec_driver_sql(SCHEMA_SQL.read_text(encoding="utf-8"), execution_options={"no_parameters": True})
    admin.dispose()

    eng = sa.create_engine(url, connect_args={"options": f"-c search_path={SCHEMA}"})
    t = sa.text
    with eng.begin() as c:
        c.execute(t("INSERT INTO assets (code, name, type) VALUES ('THYAO','Türk Hava Yolları','stock'), ('ASELS','Aselsan','stock')"))
        c.execute(t("INSERT INTO users (id, email) VALUES ('11111111-1111-1111-1111-111111111111', 'a@b.c')"))
        for i in range(30):  # son gün: düzeltilmiş fiyat (adj_close) ham fiyattan farklı
            adj = 250.0 if i == 29 else None
            c.execute(t("INSERT INTO prices (code, date, close, adj_close) VALUES ('THYAO', :d, :c, :a)"),
                      {"d": date(2026, 9, 1 + i), "c": 300 + i, "a": adj})
        a = "INSERT INTO analysis (code, run_date, horizon, direction, confidence, risk, regime, weights, indicators, low, mid, high) " \
            "VALUES (:code, :d, 5, 'up', :conf, 'medium', 'trend', CAST(:w AS jsonb), CAST(:i AS jsonb), 298.2, 316, 333.5)"
        w, ind = json.dumps({"timesfm": 0.6, "chronos": 0.4}), json.dumps({"rsi": 58.2})
        c.execute(t(a), {"code": "THYAO", "d": date(2026, 10, 12), "conf": 50, "w": w, "i": ind})  # eski gün
        c.execute(t(a), {"code": "THYAO", "d": date(2026, 10, 13), "conf": 68, "w": w, "i": ind})
        c.execute(t(a), {"code": "ASELS", "d": date(2026, 10, 13), "conf": 61, "w": w, "i": ind})
        c.execute(t("INSERT INTO signals (user_id, code, side, horizon, confidence, created_at) VALUES "
                    "('11111111-1111-1111-1111-111111111111', 'THYAO', 'buy', 5, 68, '2026-10-13 21:00+00')"))
        c.execute(t("INSERT INTO watchlist (user_id, code) VALUES ('11111111-1111-1111-1111-111111111111', 'ASELS')"))
    yield sessionmaker(bind=eng, expire_on_commit=False), eng

    eng.dispose()
    cleanup = sa.create_engine(url)
    with cleanup.begin() as conn:
        conn.execute(sa.text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
    cleanup.dispose()


def test_analysis_ve_fiyatlar_okunur(pg):
    from app.ai.db import DbAnalysisSource

    src = DbAnalysisSource(pg[0])
    a = asyncio.run(src.get_analysis("thyao", 5))
    assert a["run_date"] == "2026-10-13" and a["confidence"] == 68  # en son gün
    assert a["range"]["high"] == 333.5 and a["weights"]["timesfm"] == 0.6
    prices = asyncio.run(src.get_recent_prices("THYAO", 20))
    assert len(prices) == 20 and prices[0]["date"] < prices[-1]["date"]  # eskiden yeniye
    assert prices[-1]["close"] == 250.0 and prices[-2]["close"] == 328.0  # adj_close öncelikli, yoksa close
    assert asyncio.run(src.get_analysis("YOK", 5)) is None


def test_gece_hedefleri_sinyal_ve_izleme(pg):
    from app.ai.db import DbExplainSource

    src = DbExplainSource(pg[0])
    assert src.resolve_run_date() == "2026-10-13"
    t = {x.code: x for x in src.targets()}
    assert set(t) == {"THYAO", "ASELS"}
    assert t["THYAO"].has_signal and not t["THYAO"].watched
    assert t["ASELS"].watched and not t["ASELS"].has_signal


def test_yorumlar_upsert_edilir(pg):
    from sqlalchemy import text

    from app.ai.db import DbExplanationSink

    sink = DbExplanationSink(pg[0])
    sink.save([Explanation(code="THYAO", run_date="2026-10-13", horizon=5, text="ilk metin", source="template")])
    sink.save([Explanation(code="THYAO", run_date="2026-10-13", horizon=5, text="yeni metin", source="llm")])
    with pg[1].connect() as c:
        rows = c.execute(text("SELECT text FROM ai_explanations WHERE code='THYAO'")).all()
    assert [r[0] for r in rows] == ["yeni metin"]
