"""Gece zinciri: sıra, bağımlılık, kaldığı yerden devam, tatil — sahte adım çalıştırıcıyla."""

from datetime import date, datetime, time, timedelta

import pytest
from sqlalchemy import create_engine, text

from app.core.clock import TR
from app.jobs import nightly
from app.jobs.nightly import Result

CFG = nightly.load_config()
DAYS = [date(2026, 8, 11), date(2026, 8, 12)]  # Salı, Çarşamba


class FakeRunner:
    def __init__(self, fail: set[str] = frozenset()):
        self.fail, self.calls = set(fail), []

    def __call__(self, step, day):
        self.calls.append(step.job)
        return Result(code=1 if step.job in self.fail else 0, seconds=0.1, tail=f"{step.job} çıktısı")


@pytest.fixture(scope="module")
def eng(database):
    e = create_engine(database)
    yield e
    with e.begin() as c:
        c.execute(text("DELETE FROM job_runs WHERE run_date = ANY(:d)"), {"d": DAYS})
    e.dispose()


def _rows(eng, day):
    with eng.connect() as c:
        return c.execute(
            text("SELECT job_name, status, error, stats FROM job_runs WHERE run_date = :d ORDER BY id"),
            {"d": day},
        ).all()


def test_yapilandirma():
    jobs = [s.job for s in CFG.steps]
    assert jobs == ["collect", "forecast", "engine", "signals", "explain", "push"]
    assert [s.at for s in CFG.steps] == sorted(s.at for s in CFG.steps)  # saatler sıralı
    assert CFG.deferred_push.at == time(8, 5)
    assert nightly.is_trading_day(date(2026, 10, 14), CFG)
    assert not nightly.is_trading_day(date(2026, 10, 17), CFG)  # cumartesi
    assert not nightly.is_trading_day(date(2026, 10, 29), CFG)  # Cumhuriyet Bayramı


def test_basarili_zincir(eng):
    run = FakeRunner()
    st = nightly.run_chain(eng, DAYS[0], CFG, runner=run, wait=False)
    assert run.calls == ["collect", "forecast", "engine", "signals", "push"]  # explain kapalı
    assert st["explain"] == "disabled" and st["push"] == "success"
    # Kendi kaydını yazmayan adımların job_runs satırını zincir yazar
    rows = {r.job_name: r for r in _rows(eng, DAYS[0])}
    assert set(rows) == {"collect", "forecast"}
    assert rows["collect"].status == "success" and rows["collect"].stats["exit_code"] == 0


def test_hata_zinciri_keser_sonra_kaldigi_yerden_devam(eng):
    run = FakeRunner(fail={"forecast"})
    st = nightly.run_chain(eng, DAYS[1], CFG, runner=run, wait=False)
    assert run.calls == ["collect", "forecast"]
    assert st == {
        "collect": "success",
        "forecast": "failed",
        "engine": "skipped",
        "signals": "skipped",
        "explain": "disabled",
        "push": "skipped",
    }
    rows = _rows(eng, DAYS[1])
    skipped = [r for r in rows if r.job_name == "engine"]
    assert skipped[0].status == "failed" and "forecast" in skipped[0].error
    assert "çıkış kodu 1" in next(r.error for r in rows if r.job_name == "forecast")

    # Sorun giderildi, zincir yeniden başlatıldı: collect tekrar çalışmaz
    run2 = FakeRunner()
    st2 = nightly.run_chain(eng, DAYS[1], CFG, runner=run2, wait=False)
    assert run2.calls == ["forecast", "engine", "signals", "push"]
    assert st2["collect"] == "done"


def test_tatilde_calismaz(eng):
    run = FakeRunner()
    assert nightly.run_chain(eng, date(2026, 8, 15), CFG, runner=run, wait=False) == {}
    assert run.calls == []


def test_adim_saatini_bekler():
    now = [datetime.combine(date(2026, 8, 11), time(18, 58), TR)]
    slept = []

    def sleep(s):
        slept.append(s)
        now[0] += timedelta(seconds=s)

    nightly._sleep_until(time(19, 0), date(2026, 8, 11), lambda: now[0], sleep)
    assert sum(slept) == 120 and max(slept) <= 60
    slept.clear()
    nightly._sleep_until(time(19, 0), date(2026, 8, 11), lambda: now[0], sleep)  # saat geçtiyse beklemez
    assert slept == []


def test_ertelenmis_bildirim_tarihsiz_calisir():
    seen = []
    nightly.run_deferred_push(CFG, runner=lambda step, day: seen.append((step.cmd, day)) or Result(0, 0))
    assert seen == [(["-m", "app.jobs.push"], None)]
