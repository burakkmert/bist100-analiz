"""Aşama 2: "bu sinyal neden?" (/signals/{id}/explain) ve sanal portföy (/paper-portfolio)."""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, text

from tests.utils import auth_header, make_token

CODE = "ASM2A"
RD = date(2026, 7, 10)  # Cuma


def _user(client):
    uid = uuid.uuid4()
    h = auth_header(make_token(uid, email=f"a2-{uid.hex[:8]}@example.com"))
    assert client.get("/me/profile", headers=h).status_code == 200
    return uid, h


@pytest.fixture(scope="module")
def ctx(database):
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    eng = create_engine(database)
    with eng.begin() as c:
        c.execute(
            text("INSERT INTO assets(code, name, type) VALUES (:c, :n, 'fund')"), {"c": CODE, "n": "A2"}
        )
        c.execute(
            text("INSERT INTO prices(code, date, close, adj_close) VALUES (:c, :d, :p, :p)"),
            [
                {"c": CODE, "d": RD - timedelta(days=1), "p": 99.0},
                {"c": CODE, "d": RD, "p": 100.0},  # giriş
                {"c": CODE, "d": RD + timedelta(days=3), "p": 112.0},  # son kapanış
            ],
        )
        c.execute(
            text(
                "INSERT INTO analysis(code, run_date, horizon, direction, confidence, risk, regime, weights, "
                "indicators, low, mid, high) VALUES (:c, :rd, 5, 'up', 78, 'low', 'trend', "
                "CAST(:w AS jsonb), CAST(:i AS jsonb), 98, 106, 114)"
            ),
            {
                "c": CODE,
                "rd": RD,
                "w": '{"timesfm": 0.5, "chronos": 0.3, "naive_drift": 0.2}',
                "i": '{"rsi": 55.1, "market_regime": "range", "confidence_parts": {"base": 30}, '
                '"calibration": {"shown": true, "hit_rate": 0.9}}',
            },
        )
        c.execute(
            text("INSERT INTO ai_explanations VALUES (:c, :rd, 5, 'Model yükseliş yönlü.')"),
            {"c": CODE, "rd": RD},
        )
    u1, h1 = _user(client)
    _, h2 = _user(client)

    def sig(outcome, created_day, qty=10):
        with eng.begin() as c:
            return c.execute(
                text(
                    "INSERT INTO signals(user_id, code, side, horizon, confidence, suggested_qty, "
                    "created_at, outcome) VALUES (:u, :c, 'buy', 5, 78, :q, "
                    "(CAST(:d AS date) + TIME '21:30') AT TIME ZONE 'Europe/Istanbul', "
                    "CAST(:o AS jsonb)) RETURNING id"
                ),
                {"u": u1, "c": CODE, "q": qty, "d": created_day, "o": outcome},
            ).scalar()

    open_id = sig(None, RD)
    closed_id = sig('{"entry": 100, "realized": 95, "hit": false, "evaluated_on": "2026-07-17"}', RD, qty=2)
    yield {"client": client, "h1": h1, "h2": h2, "open_id": open_id, "closed_id": closed_id}
    with eng.begin() as c:
        for t in ("signals", "ai_explanations", "analysis", "prices", "assets"):
            c.execute(text(f"DELETE FROM {t} WHERE code = :c"), {"c": CODE})
    eng.dispose()


def test_explain_bilesenleri_dondurur(ctx):
    r = ctx["client"].get(f"/signals/{ctx['open_id']}/explain", headers=ctx["h1"])
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["run_date"] == str(RD) and b["direction"] == "up" and b["confidence"] == 78
    assert b["weights"]["timesfm"] == 0.5 and b["confidence_parts"]["base"] == 30
    assert b["market_regime"] == "range" and b["calibration"]["hit_rate"] == 0.9
    assert b["indicators"] == {"rsi": 55.1}  # ayrı alanlardakiler tekrar edilmez
    assert b["band"] == {"low": 98.0, "mid": 106.0, "high": 114.0}
    assert b["comment"] == "Model yükseliş yönlü." and "tavsiyesi değildir" in b["disclaimer"]


def test_explain_baskasinin_sinyali_404(ctx):
    assert ctx["client"].get(f"/signals/{ctx['open_id']}/explain", headers=ctx["h2"]).status_code == 404
    assert ctx["client"].get("/signals/999999999/explain", headers=ctx["h1"]).status_code == 404


def test_sanal_portfoy(ctx):
    b = ctx["client"].get("/paper-portfolio", headers=ctx["h1"]).json()
    pos = {p["signal_id"]: p for p in b["positions"]}
    o, k = pos[ctx["open_id"]], pos[ctx["closed_id"]]
    assert o["closed"] is False and o["entry"] == 100 and o["last_price"] == 112 and o["pnl"] == 120
    assert k["closed"] is True and k["exit"] == 95 and k["pnl"] == -10 and k["closed_on"] == "2026-07-17"
    s = b["summary"]
    assert s["positions"] == 2 and s["open"] == 1 and s["closed"] == 1
    assert s["invested"] == 1200 and s["pnl"] == 110 and s["hit_rate"] == 0
    assert "yatırım tavsiyesi değildir" in b["note"]
    assert ctx["client"].get("/paper-portfolio", headers=ctx["h2"]).json()["positions"] == []
    assert ctx["client"].get("/paper-portfolio").status_code == 401
