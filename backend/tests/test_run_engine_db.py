"""Gece karar motoru — gerçek veritabanıyla uçtan uca:
veri yükle → engine.run_engine.run → analysis + job_runs →
/assets/{code}/analysis motorun çıktısını gösterir."""

import uuid
from datetime import date, timedelta

import numpy as np
import pytest
from sqlalchemy import create_engine, text

from app.api import assets as assets_api
from engine import run_engine
from tests.utils import auth_header, make_token

STOCK, FUND, NOFC = "RENGA", "RENGF", "RENGX"
CODES = (STOCK, FUND, NOFC)
RD = date(2026, 10, 9)  # Cuma


@pytest.fixture(scope="module")
def db(database):
    eng = create_engine(database)
    rng = np.random.default_rng(3)
    days = [RD - timedelta(days=k) for k in range(420, -1, -1) if (RD - timedelta(days=k)).weekday() < 5]
    with eng.begin() as c:
        c.execute(
            text("INSERT INTO assets(code, name, type) VALUES (:c, :n, :t)"),
            [
                {"c": STOCK, "n": "Motor Test Hisse", "t": "stock"},
                {"c": FUND, "n": "Motor Test Fon", "t": "fund"},
                {"c": NOFC, "n": "Tahminsiz", "t": "stock"},
            ],
        )
        rows, last = [], {}
        for code, ohlc in ((STOCK, True), (FUND, False), (NOFC, True)):
            px = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.015, len(days))))
            last[code] = float(px[-1])
            for d, p in zip(days, px, strict=True):
                rows.append(
                    {
                        "c": code,
                        "d": d,
                        "cl": float(p),
                        "h": float(p) * 1.01 if ohlc else None,
                        "l": float(p) * 0.99 if ohlc else None,
                        "o": float(p) if ohlc else None,
                        "v": 4_000_000 if ohlc else None,
                    }
                )
        # Gelecek tarihli fiyat: motor run_date sonrasını GÖRMEMELİ (sızıntı testi)
        rows.append(
            {
                "c": STOCK,
                "d": RD + timedelta(days=3),
                "cl": last[STOCK] * 10,
                "h": None,
                "l": None,
                "o": None,
                "v": None,
            }
        )
        c.execute(
            text(
                "INSERT INTO prices(code, date, open, high, low, close, adj_close, volume) "
                "VALUES (:c, :d, :o, :h, :l, :cl, :cl, :v)"
            ),
            rows,
        )
        fc = []
        for code in (STOCK, FUND):
            for h in (1, 5, 20, 120):
                for i, m in enumerate(("timesfm", "chronos", "naive_drift", "naive")):
                    mid = last[code] * (1 + 0.012 * h**0.5 + 0.001 * i)
                    fc.append(
                        {
                            "c": code,
                            "rd": RD,
                            "m": m,
                            "h": h,
                            "p10": mid * 0.96,
                            "p50": None if h == 120 else mid,
                            "p90": mid * 1.04,
                        }
                    )
        c.execute(text("INSERT INTO forecasts VALUES (:c, :rd, :m, :h, :p10, :p50, :p90)"), fc)
        c.execute(
            text("INSERT INTO model_errors VALUES (:c, :m, 5, 60, :mae, 1, 0.6, :asof)"),
            [
                {"c": STOCK, "m": "timesfm", "mae": 1.0, "asof": RD},
                {"c": STOCK, "m": "chronos", "mae": 4.0, "asof": RD},
                # run_date'ten sonraki hata kaydı kullanılmamalı
                {"c": STOCK, "m": "chronos", "mae": 0.01, "asof": RD + timedelta(days=5)},
            ],
        )
    assets_api._list_cache.clear()
    yield eng
    with eng.begin() as c:
        for t in ("analysis", "model_errors", "forecasts", "prices", "assets"):
            c.execute(text(f"DELETE FROM {t} WHERE code = ANY(:codes)"), {"codes": list(CODES)})
        c.execute(text("DELETE FROM job_runs WHERE job_name = 'engine' AND run_date = :rd"), {"rd": RD})
    eng.dispose()


def _analysis(eng, code):
    with eng.connect() as c:
        return {
            r.horizon: r
            for r in c.execute(
                text("SELECT * FROM analysis WHERE code = :c AND run_date = :rd ORDER BY horizon"),
                {"c": code, "rd": RD},
            )
        }


def test_motor_analysis_ve_job_runs_yazar(db):
    assert run_engine.run(db, RD, list(CODES)) == 0

    a = _analysis(db, STOCK)
    assert set(a) == {1, 5, 20}  # 120 günde analiz yok
    for r in a.values():
        assert r.direction in ("up", "down", "flat") and 0 <= r.confidence <= 100
        assert r.low <= r.mid <= r.high
        assert set(r.weights) == {"timesfm", "chronos", "naive_drift"}  # 'naive' ensemble'da yok
        assert "confidence_parts" in r.indicators and "market_regime" in r.indicators
    # 1/MAE: timesfm (1.0) chronos'tan (4.0) ağır; run_date sonrası 0.01 kaydı kullanılmadı
    assert a[5].weights["timesfm"] > a[5].weights["chronos"]
    # Fon da işlendi; tahminsiz varlık atlandı
    assert set(_analysis(db, FUND)) == {1, 5, 20}
    assert _analysis(db, NOFC) == {}

    with db.connect() as c:
        job = c.execute(
            text(
                "SELECT * FROM job_runs WHERE job_name = 'engine' AND run_date = :rd ORDER BY id DESC LIMIT 1"
            ),
            {"rd": RD},
        ).one()
    assert job.status == "success" and job.finished_at is not None
    assert job.stats["ok"] == 2 and job.stats["skipped_no_forecast"] == 1


def test_gelecek_fiyat_kullanilmaz(db):
    """run_date+3 günündeki 10 katı fiyat sızsaydı son fiyat 10 kat olur, değişim (p50 − son fiyat)
    son fiyatın ~9 katı kadar eksi çıkardı. Doğru çalışmada değişim birkaç yüzde mertebesinde."""
    run_engine.run(db, RD, list(CODES))
    for r in _analysis(db, STOCK).values():
        change = r.indicators["confidence_parts"]["change"]
        assert abs(change) < 0.5 * float(r.mid), (r.horizon, change, r.mid)
        assert r.indicators["ma20"] < float(r.mid) * 1.5


def test_ikinci_calistirma_cift_kayit_uretmez(db):
    run_engine.run(db, RD, list(CODES))
    run_engine.run(db, RD, list(CODES))
    with db.connect() as c:
        n = c.execute(
            text("SELECT count(*) FROM analysis WHERE code = :c AND run_date = :rd"), {"c": STOCK, "rd": RD}
        ).scalar()
    assert n == 3


def test_dry_run_yazmaz(db):
    with db.begin() as c:
        c.execute(text("DELETE FROM analysis WHERE code = ANY(:codes)"), {"codes": list(CODES)})
    assert run_engine.run(db, RD, list(CODES), dry_run=True) == 0
    assert _analysis(db, STOCK) == {}


def test_api_motorun_ciktisini_gosterir(db, client):
    run_engine.run(db, RD, list(CODES))
    h = auth_header(make_token(email=f"{uuid.uuid4().hex[:8]}@example.com"))
    body = client.get(f"/assets/{STOCK}/analysis?horizon=5", headers=h).json()
    row = _analysis(db, STOCK)[5]
    assert body["run_date"] == str(RD)
    assert body["direction"] == row.direction and body["confidence"] == row.confidence
    assert body["indicators"]["confidence_parts"]["base"] == 30
