"""Portföy, izleme listesi, push token ve backtest özeti — gerçek veritabanıyla.
En önemli kural: kullanıcı yalnızca KENDİ kayıtlarını görür/değiştirir."""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, text

from app.core.clock import today_tr
from tests.utils import auth_header, make_token

A, B = "PRTFA", "PRTFB"
TODAY = today_tr()


def _user():
    uid = uuid.uuid4()
    return uid, auth_header(make_token(uid, email=f"{uid.hex[:10]}@example.com"))


@pytest.fixture(scope="module")
def db(database):
    eng = create_engine(database)
    with eng.begin() as c:
        c.execute(
            text("INSERT INTO assets(code, name, type) VALUES (:c, :n, :t)"),
            [{"c": A, "n": "Portföy Test A", "t": "stock"}, {"c": B, "n": "Portföy Test B", "t": "fund"}],
        )
        c.execute(
            text("INSERT INTO prices(code, date, close, adj_close) VALUES (:c, :d, :p, :p)"),
            [
                {"c": A, "d": TODAY - timedelta(days=2), "p": 100.0},
                {"c": A, "d": TODAY - timedelta(days=1), "p": 110.0},  # son kapanış
            ],
        )
    yield eng
    with eng.begin() as c:
        for t in ("positions", "signals", "watchlist", "model_errors", "prices"):
            c.execute(text(f"DELETE FROM {t} WHERE code = ANY(:codes)"), {"codes": [A, B]})
        c.execute(text("DELETE FROM assets WHERE code = ANY(:codes)"), {"codes": [A, B]})
    eng.dispose()


def _new(client, h, **kw):
    body = {"code": A, "qty": 10, "buy_price": 100, "buy_date": str(TODAY - timedelta(days=5)), **kw}
    return client.post("/portfolio", json=body, headers=h)


# --------------------------------------------------------------------------- portföy


def test_giris_olmadan_401(db, client):
    assert client.get("/portfolio").status_code == 401
    assert client.get("/watchlist").status_code == 401
    assert client.post("/devices/push-token", json={"token": "x", "platform": "ios"}).status_code == 401


def test_olustur_listele_kar_zarar(db, client):
    _, h = _user()
    r = _new(client, h, code="prtfa")  # küçük harf kabul edilir
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["code"] == A and p["id"] > 0 and p["sell_price"] is None and p["signal_id"] is None
    assert p["last_price"] == 110.0 and p["pnl"] == 100.0 and p["pnl_pct"] == 10.0

    rows = client.get("/portfolio", headers=h).json()
    assert [x["id"] for x in rows] == [p["id"]]


def test_satis_kapali_ve_durum_suzgeci(db, client):
    _, h = _user()
    a = _new(client, h).json()
    b = _new(client, h, qty=2).json()
    r = client.patch(f"/portfolio/{a['id']}", json={"sell_price": 90, "sell_date": str(TODAY)}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["pnl"] == -100.0 and r.json()["last_price"] == 90.0

    assert [x["id"] for x in client.get("/portfolio?status=open", headers=h).json()] == [b["id"]]
    assert [x["id"] for x in client.get("/portfolio?status=closed", headers=h).json()] == [a["id"]]
    assert len(client.get("/portfolio", headers=h).json()) == 2
    assert client.get("/portfolio?status=xyz", headers=h).status_code == 422


@pytest.mark.parametrize(
    "kw",
    [
        {"qty": 0},
        {"qty": -1},
        {"buy_price": 0},
        {"buy_date": str(TODAY + timedelta(days=1))},
        {"code": "YOKBOYLE"},
    ],
)
def test_olusturma_dogrulama_422(db, client, kw):
    _, h = _user()
    assert _new(client, h, **kw).status_code == 422


def test_satis_tarihi_dogrulama(db, client):
    _, h = _user()
    p = _new(client, h).json()
    before = str(TODAY - timedelta(days=6))
    assert (
        client.patch(
            f"/portfolio/{p['id']}", json={"sell_price": 1, "sell_date": before}, headers=h
        ).status_code
        == 422
    )
    future = str(TODAY + timedelta(days=1))
    assert (
        client.patch(
            f"/portfolio/{p['id']}", json={"sell_price": 1, "sell_date": future}, headers=h
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/portfolio/{p['id']}", json={"sell_price": 0, "sell_date": str(TODAY)}, headers=h
        ).status_code
        == 422
    )


def test_baska_kullanicinin_kaydi_gorunmez_degismez_silinmez(db, client):
    _, h1 = _user()
    _, h2 = _user()
    p = _new(client, h1).json()

    assert client.get("/portfolio", headers=h2).json() == []
    sell = {"sell_price": 120, "sell_date": str(TODAY)}
    assert client.patch(f"/portfolio/{p['id']}", json=sell, headers=h2).status_code == 404
    assert client.delete(f"/portfolio/{p['id']}", headers=h2).status_code == 404
    # Sahibinde hâlâ duruyor ve değişmemiş
    (mine,) = client.get("/portfolio", headers=h1).json()
    assert mine["sell_price"] is None


def test_sil(db, client):
    _, h = _user()
    p = _new(client, h).json()
    assert client.delete(f"/portfolio/{p['id']}", headers=h).status_code == 204
    assert client.get("/portfolio", headers=h).json() == []
    assert client.delete(f"/portfolio/{p['id']}", headers=h).status_code == 404


def test_signal_id_yalniz_kendi_sinyali(db, client):
    u1, h1 = _user()
    _, h2 = _user()
    client.get("/portfolio", headers=h1)  # kullanıcı kaydı oluşsun
    with db.begin() as c:
        sid = c.execute(
            text(
                "INSERT INTO signals(user_id, code, side, horizon, confidence) "
                "VALUES (:u, :c, 'buy', 5, 70) RETURNING id"
            ),
            {"u": u1, "c": A},
        ).scalar()
    assert _new(client, h1, signal_id=sid).json()["signal_id"] == sid
    assert _new(client, h2, signal_id=sid).status_code == 422  # başkasının sinyali
    assert _new(client, h1, signal_id=sid, code=B).status_code == 422  # başka varlığın sinyali


# --------------------------------------------------------------------------- izleme listesi


def test_izleme_listesi_idempotent_ve_kullaniciya_ozel(db, client):
    _, h1 = _user()
    _, h2 = _user()
    for code in (B, A, A.lower()):
        assert client.post("/watchlist", json={"code": code}, headers=h1).status_code == 204
    assert client.get("/watchlist", headers=h1).json() == [A, B]
    assert client.get("/watchlist", headers=h2).json() == []
    assert client.post("/watchlist", json={"code": "YOKBOYLE"}, headers=h1).status_code == 422

    assert client.delete(f"/watchlist/{A}", headers=h2).status_code == 204  # başkasınınkine dokunmaz
    assert client.get("/watchlist", headers=h1).json() == [A, B]
    assert client.delete(f"/watchlist/{A}", headers=h1).status_code == 204
    assert client.delete(f"/watchlist/{A}", headers=h1).status_code == 204
    assert client.get("/watchlist", headers=h1).json() == [B]


# --------------------------------------------------------------------------- push token


def test_push_token_kaydi_ve_cihaz_devri(db, client):
    u1, h1 = _user()
    u2, h2 = _user()
    tok = f"ExponentPushToken[{uuid.uuid4().hex}]"
    assert (
        client.post("/devices/push-token", json={"token": tok, "platform": "ios"}, headers=h1).status_code
        == 204
    )
    assert (
        client.post("/devices/push-token", json={"token": tok, "platform": "ios"}, headers=h1).status_code
        == 204
    )
    assert (
        client.post("/devices/push-token", json={"token": tok, "platform": "web"}, headers=h1).status_code
        == 422
    )
    # Aynı cihazda başka hesapla giriş: token yeni kullanıcıya geçer
    assert (
        client.post("/devices/push-token", json={"token": tok, "platform": "android"}, headers=h2).status_code
        == 204
    )
    with db.connect() as c:
        rows = c.execute(text("SELECT user_id, platform FROM push_tokens WHERE token = :t"), {"t": tok}).all()
    assert [(r.user_id, r.platform) for r in rows] == [(u2, "android")]


# --------------------------------------------------------------------------- backtest özeti


def test_backtest_ozeti(db, client):
    _, h = _user()
    old, new = date(2026, 9, 1), date(2026, 9, 2)
    rows = []
    for code, naive_mape, tfm_mape in ((A, 2.0, 1.0), (B, 1.0, 3.0)):
        rows += [
            {"c": code, "m": "naive", "mape": naive_mape, "acc": 0.5, "d": new},
            {"c": code, "m": "timesfm", "mape": tfm_mape, "acc": 0.6, "d": new},
            {"c": code, "m": "timesfm", "mape": 99.0, "acc": 0.1, "d": old},  # eski gün kullanılmaz
        ]
    with db.begin() as c:
        c.execute(
            text("INSERT INTO model_errors VALUES (:c, :m, 5, 60, 1.0, :mape, :acc, :d)"),
            rows,
        )
    body = client.get("/backtest/summary", headers=h).json()
    assert body["as_of"] == str(new) and body["window_days"] == 60
    m = {(x["model"], x["horizon"]): x for x in body["metrics"]}
    tfm = m[("timesfm", 5)]
    assert tfm["n_assets"] == 2 and tfm["mape"] == 2.0 and tfm["dir_acc"] == 0.6
    assert tfm["beats_naive"] == 0.5 and tfm["is_baseline"] is False
    assert m[("naive", 5)]["is_baseline"] is True and m[("naive", 5)]["beats_naive"] is None

    fund = client.get("/backtest/summary?type=fund", headers=h).json()
    assert {x["n_assets"] for x in fund["metrics"]} == {1}
    assert client.get("/backtest/summary").status_code == 401
