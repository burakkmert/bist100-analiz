"""Gece zinciri zamanlayıcısı (Görev 9): veri → tahmin → karar motoru → sinyal → yorum → bildirim.

    cd backend && python -m app.jobs.nightly --serve     # sürekli çalışır (APScheduler)
    cd backend && python -m app.jobs.nightly --once      # bugünün zinciri, adım saatlerini bekleyerek
    cd backend && python -m app.jobs.nightly --once --no-wait --date 2026-10-13   # hemen, sırayla

Bu süreç modellerin kurulu olduğu makinede (Kişi 1'in ortamı, GPU) çalışır; API sunucusundan ayrıdır.
Adımlar ve saatler nightly.yaml'da. Her adım ayrı bir alt süreçtir: biri çökerse zamanlayıcı ayakta kalır.

Kurallar
  * Hafta sonu ve tatil günlerinde zincir çalışmaz (08:05 ertelenmiş bildirim her gün çalışır).
  * Adım saatinden önce başlamaz; önceki ZORUNLU adım başarısızsa atlanır ve job_runs'a nedeniyle
    'failed' yazılır (izleme ekranında zincirin nerede koptuğu görünür).
  * O gün zaten başarılı olan adım tekrar çalışmaz (yeniden başlatmada kaldığı yerden devam).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time as _time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path

import yaml
from sqlalchemy import Engine, create_engine, text

from app.core.clock import TR, now_tr

log = logging.getLogger("jobs.nightly")

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent
CONFIG_PATH = Path(__file__).with_name("nightly.yaml")


@dataclass(frozen=True)
class Step:
    job: str
    at: time
    cmd: list[str]
    cwd: str = "repo"
    records_self: bool = False
    required: bool = True
    enabled: bool = True
    timeout_min: float = 60


@dataclass
class Config:
    steps: list[Step]
    deferred_push: Step
    holidays: set[date] = field(default_factory=set)


def _t(s: str) -> time:
    h, m = str(s).split(":")
    return time(int(h), int(m))


def load_config(path: Path = CONFIG_PATH) -> Config:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    def step(d: dict) -> Step:
        return Step(**{**d, "at": _t(d["at"])})

    return Config(
        steps=[step(s) for s in raw["steps"]],
        deferred_push=step({"job": "push", "records_self": True, **raw["deferred_push"]}),
        holidays={
            d if isinstance(d, date) else date.fromisoformat(str(d)) for d in raw.get("holidays") or []
        },
    )


def is_trading_day(d: date, cfg: Config) -> bool:
    return d.weekday() < 5 and d not in cfg.holidays


# --------------------------------------------------------------------------- alt süreç


@dataclass
class Result:
    code: int
    seconds: float
    tail: str = ""


Runner = Callable[[Step, date | None], Result]


def subprocess_runner(step: Step, day: date | None) -> Result:
    """Adımı ayrı Python süreci olarak çalıştırır. engine.* ve app.* aynı anda içe aktarılabilsin diye
    PYTHONPATH'e hem depo kökü hem backend eklenir."""
    args = [a.replace("{date}", day.isoformat()) if day else a for a in step.cmd]
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(REPO_DIR), str(BACKEND_DIR)])}
    cwd = REPO_DIR if step.cwd == "repo" else BACKEND_DIR
    t0 = _time.monotonic()
    try:
        p = subprocess.run(
            [sys.executable, *args],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=step.timeout_min * 60,
        )
        out, code = (p.stdout or "") + (p.stderr or ""), p.returncode
    except subprocess.TimeoutExpired as e:
        out, code = f"zaman aşımı ({step.timeout_min} dk): {e}", 124
    tail = out[-2000:]
    log.info("%s bitti: çıkış=%s süre=%.0fs", step.job, code, _time.monotonic() - t0)
    return Result(code=code, seconds=round(_time.monotonic() - t0, 1), tail=tail)


# --------------------------------------------------------------------------- job_runs


def _succeeded(conn, job: str, day: date) -> bool:
    return bool(
        conn.execute(
            text(
                "SELECT 1 FROM job_runs WHERE job_name = :j AND run_date = :d AND status = 'success' LIMIT 1"
            ),
            {"j": job, "d": day},
        ).first()
    )


def _record(conn, job: str, day: date, status: str, error: str | None = None, stats: dict | None = None):
    conn.execute(
        text(
            "INSERT INTO job_runs (job_name, run_date, finished_at, status, error, stats) "
            "VALUES (:j, :d, now(), :s, :e, CAST(:st AS jsonb))"
        ),
        {"j": job, "d": day, "s": status, "e": error, "st": json.dumps(stats) if stats else None},
    )


def _sleep_until(at: time, day: date, clock: Callable[[], datetime], sleep: Callable[[float], None]) -> None:
    target = datetime.combine(day, at, TR)
    while (left := (target - clock()).total_seconds()) > 0:
        sleep(min(left, 60))


# --------------------------------------------------------------------------- zincir


def run_chain(
    engine: Engine,
    day: date,
    cfg: Config | None = None,
    runner: Runner = subprocess_runner,
    clock: Callable[[], datetime] = now_tr,
    sleep: Callable[[float], None] = _time.sleep,
    wait: bool = True,
) -> dict[str, str]:
    """Bir günün zinciri. Dönüş: {adım: 'success' | 'failed' | 'skipped' | 'done' | 'disabled'}."""
    cfg = cfg or load_config()
    status: dict[str, str] = {}
    if not is_trading_day(day, cfg):
        log.info("%s işlem günü değil (hafta sonu/tatil); zincir çalışmadı", day)
        return status

    broken: str | None = None  # başarısız zorunlu adım
    for step in cfg.steps:
        if not step.enabled:
            status[step.job] = "disabled"
            continue
        with engine.connect() as conn:
            if _succeeded(conn, step.job, day):
                status[step.job] = "done"
                continue
        if broken:
            with engine.begin() as conn:
                _record(conn, step.job, day, "failed", f"atlandı: önceki adım ({broken}) başarısız")
            status[step.job] = "skipped"
            continue
        if wait:
            _sleep_until(step.at, day, clock, sleep)

        log.info("%s başlıyor (%s)", step.job, day)
        res = runner(step, day)
        ok = res.code == 0
        if not step.records_self:
            with engine.begin() as conn:
                _record(
                    conn,
                    step.job,
                    day,
                    "success" if ok else "failed",
                    None if ok else f"çıkış kodu {res.code}\n{res.tail}"[-1000:],
                    {"exit_code": res.code, "seconds": res.seconds, "log_tail": res.tail[-500:]},
                )
        status[step.job] = "success" if ok else "failed"
        if not ok and step.required:
            broken = step.job
    log.info("%s zinciri: %s", day, status)
    return status


def run_deferred_push(cfg: Config | None = None, runner: Runner = subprocess_runner) -> int:
    """08:05: sessiz saatte bekleyen bildirimler + receipt kontrolü (push kendi tarihini bulur)."""
    cfg = cfg or load_config()
    return runner(cfg.deferred_push, None).code


def serve(engine: Engine, cfg: Config | None = None) -> None:  # pragma: no cover — sonsuz döngü
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    cfg = cfg or load_config()
    first = min(s.at for s in cfg.steps if s.enabled)
    sched = BlockingScheduler(timezone=TR)
    sched.add_job(
        lambda: run_chain(engine, now_tr().date(), cfg),
        CronTrigger(day_of_week="mon-fri", hour=first.hour, minute=first.minute, timezone=TR),
        id="nightly",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3 * 3600,  # makine geç açıldıysa o gece yine çalışsın
    )
    sched.add_job(
        lambda: run_deferred_push(cfg),
        CronTrigger(hour=cfg.deferred_push.at.hour, minute=cfg.deferred_push.at.minute, timezone=TR),
        id="deferred_push",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=2 * 3600,
    )
    log.info(
        "Zamanlayıcı başladı: zincir hafta içi %s, ertelenmiş bildirim her gün %s",
        first,
        cfg.deferred_push.at,
    )
    sched.start()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Gece zinciri zamanlayıcısı")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--serve", action="store_true", help="Sürekli çalış (hafta içi her gece)")
    g.add_argument("--once", action="store_true", help="Bir günün zincirini çalıştır ve çık")
    p.add_argument("--date", type=date.fromisoformat, help="--once için gün (varsayılan: bugün)")
    p.add_argument("--no-wait", action="store_true", help="--once: adım saatlerini bekleme")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL gerekli", file=sys.stderr)
        return 2
    engine = create_engine(url)
    if args.serve:
        serve(engine)
        return 0
    st = run_chain(engine, args.date or now_tr().date(), wait=not args.no_wait)
    return 1 if "failed" in st.values() or "skipped" in st.values() else 0


if __name__ == "__main__":
    sys.exit(main())
