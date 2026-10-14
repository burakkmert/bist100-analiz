"""Gece sinyal motoru — gerçek veritabanıyla uçtan uca:
analysis + profil/izleme/portföy → engine.run_signals.run → signals + job_runs →
/signals ve /signals/track-record. Ufuk dolunca outcome doldurulur."""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, text

from engine import run_engine, run_signals
from tests.utils import auth_header, make_token

UP, WEAK, HELD = "SIGUP", "SIGWK", "SIGHD"
CODES = [UP, WEAK, HELD]
RD = date(2026, 9, 18)  # Cuma; diğer testlerin gecesiyle çakışmasın


def _bdays(start: date, n: int) -> list[date]:
    out, d = [], start
    while len(out) < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            out.append(d)
    return out


def _user(client, **profile):
    uid = uuid.uuid4()
    h = auth_header(make_token(uid, email=f"sig-{uid.hex[:8]}@example.com"))
    assert client.put("/me/profile", json=profile, headers=h).status_code == 200
    return uid, h


@pytest.fixture(scope="module")
def ctx(database):
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    eng = create_engine(database)
    with eng.begin() as c:
        c.execute(
            text("INSERT INTO assets(code, name, type) VALUES (:c, :n, 'stock')"),
            [{"c": code, "n": code} for code in CODES],
        )
        past = [RD - timedelta(days=k) for k in range(10, -1, -1)]
        c.execute(
            text("INSERT INTO prices(code, date, close, adj_close) VALUES (:c, :d, 100, 100)"),
            [{"c": code, "d": d} for code in CODES for d in past],
        )
        a = [
            # (kod, yön, güven, risk)
            (UP, "up", 80, "low"),
            (WEAK, "up", 60, "low"),  # dengeli eşiğin (65) altında
            (HELD, "down", 80, "medium"),
        ]
        c.execute(
            text(
                "INSERT INTO analysis(code, run_date, horizon, direction, confidence, risk, regime, "
                "indicators, low, mid, high) VALUES (:c, :rd, 5, :d, :conf, :r, 'trend', "
                "CAST('{\"atr_pct\": 2.0}' AS jsonb), 95, 101, 120)"
            ),
            [{"c": x[0], "rd": RD, "d": x[1], "conf": x[2], "r": x[3]} for x in a],
        )

    u1, h1 = _user(client, risk_profile="balanced", budget=10000)
    for code in (UP, WEAK):
        assert client.post("/watchlist", json={"code": code}, headers=h1).status_code == 204
    pos = {"code": HELD, "qty": 5, "buy_price": 100, "buy_date": str(RD - timedelta(days=10))}
    assert client.post("/portfolio", json=pos, headers=h1).status_code == 201
    u2, h2 = _user(client, risk_profile="cautious", budget=5000)  # izleme yok; evren eşiği 85

    # Kurallar kalibrasyondan bağımsız sınansın (eşleme dosyası depoya girse bile)
    original = run_engine.load_calibration
    run_engine.load_calibration = lambda cfg: None
    yield {"eng": eng, "client": client, "h1": h1, "h2": h2, "u1": u1}
    run_engine.load_calibration = original

    with eng.begin() as c:
        for t in ("positions", "watchlist", "signals", "analysis", "prices"):
            c.execute(text(f"DELETE FROM {t} WHERE code = ANY(:codes)"), {"codes": CODES})
        c.execute(text("DELETE FROM assets WHERE code = ANY(:codes)"), {"codes": CODES})
        c.execute(text("DELETE FROM job_runs WHERE job_name = 'signals' AND run_date >= :rd"), {"rd": RD})
    eng.dispose()


def _mine(eng, uid):
    with eng.connect() as c:
        return c.execute(
            text("SELECT * FROM signals WHERE user_id = :u AND code = ANY(:codes) ORDER BY side"),
            {"u": uid, "codes": CODES},
        ).all()


def test_sinyaller_uretilir_ve_kurallara_uyar(ctx):
    eng, u1 = ctx["eng"], ctx["u1"]
    assert run_signals.run(eng, RD) == 0

    rows = _mine(eng, u1)
    assert [(r.code, r.side) for r in rows] == [(UP, "buy"), (HELD, "sell")]
    buy, sell = rows
    assert buy.horizon == 5 and buy.confidence == 80
    assert float(buy.suggested_qty) == 10  # 10 000 TL × %10 / 100 TL
    assert float(buy.stop_level) == 96  # 100 − 2 × ATR(2 TL)
    assert float(sell.suggested_qty) == 5  # pozisyonun tamamı

    with eng.connect() as c:
        job = c.execute(
            text(
                "SELECT * FROM job_runs WHERE job_name = 'signals' AND run_date = :rd "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"rd": RD},
        ).one()
    assert job.status == "success"
    assert {buy.id, sell.id} <= set(job.stats["signal_ids"])


def test_api_yalniz_kendi_sinyallerini_gosterir(ctx):
    client = ctx["client"]
    mine = client.get("/signals?status=open", headers=ctx["h1"]).json()
    assert {(s["code"], s["side"]) for s in mine if s["code"] in CODES} == {(UP, "buy"), (HELD, "sell")}
    assert all(s["outcome"] is None for s in mine)
    other = client.get("/signals", headers=ctx["h2"]).json()
    assert [s for s in other if s["code"] in CODES] == []  # temkinli + izleme yok → sinyal yok
    assert client.get("/signals").status_code == 401


def test_ayni_gece_tekrar_calisinca_cift_sinyal_yok(ctx):
    run_signals.run(ctx["eng"], RD)
    assert len(_mine(ctx["eng"], ctx["u1"])) == 2


def test_ufuk_dolunca_sonuc_ve_sicil(ctx):
    eng, client = ctx["eng"], ctx["client"]
    after = _bdays(RD, 6)
    with eng.begin() as c:
        c.execute(
            text("INSERT INTO prices(code, date, close, adj_close) VALUES (:c, :d, :p, :p)"),
            [{"c": UP, "d": d, "p": 105} for d in after] + [{"c": HELD, "d": d, "p": 90} for d in after],
        )
    run_signals.run(eng, after[-1])

    buy, sell = _mine(eng, ctx["u1"])
    assert buy.outcome["hit"] is True and buy.outcome["realized"] == 105
    assert buy.outcome["evaluated_on"] == str(after[4])  # 5. işlem günü
    assert sell.outcome["hit"] is True and sell.outcome["return_pct"] == -10

    h1 = ctx["h1"]
    assert {s["code"] for s in client.get("/signals?status=closed", headers=h1).json()} >= {UP, HELD}
    rec = client.get("/signals/track-record", headers=h1).json()
    assert rec["mine"]["closed"] == 2 and rec["mine"]["hits"] == 2 and rec["mine"]["hit_rate"] == 1
    assert rec["mine"]["avg_return_pct"] == 7.5  # (+5 alım, +10 satış yönünde)
    assert {(b["side"], b["horizon"]) for b in rec["mine_by"]} == {("buy", None), ("sell", None), (None, 5)}
    assert rec["model"]["closed"] >= 2
