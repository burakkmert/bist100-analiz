"""Push bildirimi: saf kurallar + gerçek veritabanıyla uçtan uca (sahte Expo istemcisiyle)."""

import re
import uuid
from datetime import date, datetime, time, timedelta

import pytest
from sqlalchemy import create_engine, text

from app.core.clock import TR
from app.jobs import push
from app.jobs.push import PendingSignal, in_quiet_hours, make_plan, message_text
from tests.utils import auth_header, make_token

# --------------------------------------------------------------------------- saf kurallar


@pytest.mark.parametrize(
    "quiet, at, expected",
    [
        ({"start": "22:30", "end": "08:00"}, time(23, 0), True),
        ({"start": "22:30", "end": "08:00"}, time(7, 59), True),
        ({"start": "22:30", "end": "08:00"}, time(8, 0), False),
        ({"start": "22:30", "end": "08:00"}, time(22, 15), False),
        ({"start": "13:00", "end": "14:00"}, time(13, 30), True),
        ({"start": "13:00", "end": "14:00"}, time(14, 30), False),
        ({"start": "10:00", "end": "10:00"}, time(10, 0), False),
        (None, time(3, 0), False),
    ],
)
def test_sessiz_saat(quiet, at, expected):
    assert in_quiet_hours(quiet, at) is expected


def test_mesaj_metni_spk_uyumlu():
    t = message_text("THYAO", "buy", 5, 72)
    assert t == "THYAO · 5 günlük ufukta yükseliş yönlü model sinyali · güven 72"
    for side in ("buy", "sell"):
        assert not re.search(r"\b(al|sat|alın|satın)\b", message_text("X", side, 1, 60), re.I)


def _sig(i, uid, side="buy", conf=70):
    return PendingSignal(i, uid, f"K{i}", side, 5, conf)


def test_plan_sinir_once_satis_sonra_guven():
    sigs = [_sig(1, "u", conf=70), _sig(2, "u", conf=90), _sig(3, "u", side="sell", conf=40)]
    plan = make_plan(sigs, {"u": {"daily_push_limit": 2}}, {"u": ["ExponentPushToken[a]"]}, {}, time(22, 15))
    assert [s.id for s, _ in plan.send] == [3, 2] and plan.limited == [1]
    # Daha önce bu gece 1 bildirim gitmişse yalnızca 1 yer kalır
    plan = make_plan(
        sigs, {"u": {"daily_push_limit": 2}}, {"u": ["ExponentPushToken[a]"]}, {"u": 1}, time(22, 15)
    )
    assert [s.id for s, _ in plan.send] == [3]
    # Sınır 0 → hiç bildirim yok
    assert sorted(make_plan(sigs, {"u": {"daily_push_limit": 0}}, {}, {}, time(22, 15)).limited) == [1, 2, 3]


def test_plan_sessiz_saat_ve_token():
    sigs = [_sig(1, "q"), _sig(2, "n"), _sig(3, "x")]
    plan = make_plan(
        sigs,
        {"q": {"quiet_hours": {"start": "22:00", "end": "08:00"}}},
        {"q": ["ExponentPushToken[q]"], "x": ["gecersiz-token"]},
        {},
        time(22, 15),
    )
    assert plan.deferred == [1] and sorted(plan.no_token) == [2, 3] and plan.send == []


# --------------------------------------------------------------------------- uçtan uca

RD = date(2026, 8, 14)  # Cuma
CODE = "PUSHA"


class FakeExpo:
    def __init__(self):
        self.sent: list[dict] = []
        self.receipt_calls: list[list[str]] = []
        self.receipt_answer: dict[str, dict] = {}

    def send(self, messages):
        self.sent += messages
        out = []
        for m in messages:
            if "bad" in m["to"]:
                out.append({"status": "error", "details": {"error": "DeviceNotRegistered"}})
            else:
                out.append({"status": "ok", "id": f"t-{uuid.uuid4().hex[:8]}"})
        return out

    def receipts(self, ids):
        self.receipt_calls.append(list(ids))
        return {i: self.receipt_answer.get(i, {"status": "ok"}) for i in ids}


def _user(client, **profile):
    uid = uuid.uuid4()
    h = auth_header(make_token(uid, email=f"push-{uid.hex[:8]}@example.com"))
    assert client.put("/me/profile", json=profile, headers=h).status_code == 200
    return uid, h


def _token(client, h, tok):
    assert (
        client.post("/devices/push-token", json={"token": tok, "platform": "ios"}, headers=h).status_code
        == 204
    )


def _at(d: date, hh: int, mm: int) -> datetime:
    return datetime.combine(d, time(hh, mm), TR)


@pytest.fixture(scope="module")
def ctx(database):
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    eng = create_engine(database)
    with eng.begin() as c:
        c.execute(text("INSERT INTO assets(code, name, type) VALUES (:c, :c, 'stock')"), {"c": CODE})

    ua, ha = _user(client, daily_push_limit=2)
    tag = uuid.uuid4().hex[:6]
    good, bad = f"ExponentPushToken[good-{tag}]", f"ExponentPushToken[bad-{tag}]"
    _token(client, ha, good)
    _token(client, ha, bad)
    uq, hq = _user(client, quiet_hours={"start": "22:00", "end": "08:00"})
    quiet_tok = f"ExponentPushToken[quiet-{tag}]"
    _token(client, hq, quiet_tok)
    un, _ = _user(client)  # cihaz kaydı yok

    def sig(uid, side, conf):
        return c.execute(
            text(
                "INSERT INTO signals(user_id, code, side, horizon, confidence, created_at) "
                "VALUES (:u, :c, :s, 5, :conf, "
                "(CAST(:rd AS date) + TIME '21:30') AT TIME ZONE 'Europe/Istanbul') "
                "RETURNING id"
            ),
            {"u": uid, "c": CODE, "s": side, "conf": conf, "rd": RD},
        ).scalar()

    with eng.begin() as c:
        ids = {
            "a70": sig(ua, "buy", 70),
            "a80": sig(ua, "buy", 80),
            "asell": sig(ua, "sell", 50),
            "quiet": sig(uq, "buy", 75),
            "notok": sig(un, "buy", 75),
        }
        c.execute(
            text(
                "INSERT INTO job_runs(job_name, run_date, finished_at, status) "
                "VALUES ('signals', :rd, now(), 'success')"
            ),
            {"rd": RD},
        )
    yield {"eng": eng, "ids": ids, "good": good, "bad": bad, "quiet_tok": quiet_tok}
    with eng.begin() as c:
        c.execute(text("DELETE FROM signals WHERE code = :c"), {"c": CODE})
        c.execute(text("DELETE FROM assets WHERE code = :c"), {"c": CODE})
        c.execute(
            text("DELETE FROM job_runs WHERE job_name IN ('signals', 'push') AND run_date = :rd"), {"rd": RD}
        )
    eng.dispose()


def _tokens(eng, tok):
    with eng.connect() as c:
        return c.execute(text("SELECT count(*) FROM push_tokens WHERE token = :t"), {"t": tok}).scalar()


def _last_push(eng):
    with eng.connect() as c:
        return c.execute(
            text(
                "SELECT * FROM job_runs WHERE job_name = 'push' AND run_date = :rd ORDER BY id DESC LIMIT 1"
            ),
            {"rd": RD},
        ).one()


def test_gece_gonderimi(ctx):
    eng, ids = ctx["eng"], ctx["ids"]
    fake = FakeExpo()
    assert push.run(eng, RD, fake, now=_at(RD, 22, 15)) == 0

    # Kullanıcı A: sınır 2 → önce satış yönlü, sonra güveni yüksek alım; iki cihaza
    sent = {(m["data"]["signal_id"], m["to"]) for m in fake.sent}
    assert sent == {(ids[k], t) for k in ("asell", "a80") for t in (ctx["good"], ctx["bad"])}
    m = next(m for m in fake.sent if m["data"]["signal_id"] == ids["a80"])
    assert m["body"].startswith(f"{CODE} · 5 günlük ufukta yükseliş yönlü model sinyali · güven 80")
    assert "Yatırım tavsiyesi değildir" in m["body"] and m["data"]["code"] == CODE

    st = _last_push(eng).stats
    assert sorted(st["sent_signal_ids"]) == sorted([ids["asell"], ids["a80"]])
    assert st["limited_ids"] == [ids["a70"]]
    assert st["deferred_ids"] == [ids["quiet"]] and st["no_token_ids"] == [ids["notok"]]
    assert len(st["tickets"]) == 2 and st["removed_tokens"] == 1
    assert _tokens(eng, ctx["bad"]) == 0 and _tokens(eng, ctx["good"]) == 1  # geçersiz cihaz silindi


def test_tekrar_calisinca_cift_bildirim_yok(ctx):
    fake = FakeExpo()
    push.run(ctx["eng"], RD, fake, now=_at(RD, 22, 20))
    assert fake.sent == []


def test_sessiz_saat_sabah_gonderilir(ctx):
    fake = FakeExpo()
    push.run(ctx["eng"], None, fake, now=_at(RD + timedelta(days=1), 8, 5))  # tarih: son sinyal gecesi
    assert [(m["data"]["signal_id"], m["to"]) for m in fake.sent] == [(ctx["ids"]["quiet"], ctx["quiet_tok"])]


def test_bayat_sinyal_gonderilmez_ve_receipt_kontrolu(ctx):
    eng = ctx["eng"]
    fake = FakeExpo()
    with eng.connect() as c:
        tickets = {}
        for (st,) in c.execute(
            text("SELECT stats FROM job_runs WHERE job_name = 'push' AND run_date = :rd"), {"rd": RD}
        ):
            tickets.update(st.get("tickets") or {})
    quiet_ticket = next(t for t, tok in tickets.items() if tok == ctx["quiet_tok"])
    fake.receipt_answer = {quiet_ticket: {"status": "error", "details": {"error": "DeviceNotRegistered"}}}

    # Gerçek saatten 1 saat sonrası: önceki gönderimlerin receipt'leri hazır, sinyaller bayat
    push.run(eng, RD, fake, now=datetime.now(TR) + timedelta(hours=1))
    assert fake.sent == []
    assert sorted(fake.receipt_calls[0]) == sorted(tickets)
    assert _tokens(eng, ctx["quiet_tok"]) == 0
    st = _last_push(eng).stats
    assert st["stale"] is True and st["receipts"]["removed_tokens"] == 1

    # İkinci kez sorulmaz
    fake2 = FakeExpo()
    push.run(eng, RD, fake2, now=datetime.now(TR) + timedelta(hours=1))
    assert fake2.receipt_calls == []
