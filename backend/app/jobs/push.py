"""Gece push bildirimi (Görev 8) — engine.run_signals'tan sonra (22:15) ve sessiz saat ertelemesi için 08:05.

    cd backend && python -m app.jobs.push                    # son sinyal gecesi
    cd backend && python -m app.jobs.push --date 2026-10-13
    cd backend && python -m app.jobs.push --dry-run          # gönderme, yalnızca planı yaz

Kurallar
  * Bir sinyal en fazla BİR KEZ bildirilir. signals tablosunda "bildirildi" sütunu yok (sözleşme değişmesin
    diye); gönderilen sinyal id'leri job_runs('push').stats.sent_signal_ids'e yazılır ve sonraki
    çalıştırmalar bunları atlar.
  * Sessiz saatteki kullanıcının bildirimi ertelenir; 08:05 çalıştırması gönderir. Sinyal
    `MAX_AGE_HOURS`'tan eskiyse artık gönderilmez (bayat bildirim yok).
  * Kullanıcı başına gecelik üst sınır = profiles.daily_push_limit (boşsa 5, 0 = hiç).
    Önce satış yönlü (portföydeki pozisyon), sonra güveni yüksek olan; sınırı aşanlar bir daha denenmez.
  * Expo'nun bildirdiği "DeviceNotRegistered" token'lar silinir (hem ticket'ta hem receipt'te).
  * Metin "al/sat" demez: "THYAO · 5 günlük ufukta yükseliş yönlü model sinyali · güven 72" (SPK).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from sqlalchemy import Engine, create_engine, text

from app.core.clock import TR, now_tr
from app.core.config import get_settings
from app.jobs.expo import ExpoClient, PushClient, is_expo_token

log = logging.getLogger("jobs.push")

TZ = "Europe/Istanbul"
SIGNAL_TIME = time(21, 30)  # run_signals sinyalleri bu saatle yazar
MAX_AGE_HOURS = 14  # 21:30 sinyali en geç ertesi gün 11:30'a kadar bildirilebilir
DEFAULT_DAILY_LIMIT = 5
RECEIPT_MIN_AGE = timedelta(minutes=15)  # Expo: receipt'ler gönderimden ~15 dk sonra hazır olur
DISCLAIMER = "Yatırım tavsiyesi değildir."


# --------------------------------------------------------------------------- saf kurallar


def _hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def in_quiet_hours(quiet: dict | None, at: time) -> bool:
    """{"start": "22:30", "end": "08:00"} — gece yarısını geçebilir. start == end → sessiz saat yok."""
    if not quiet or not quiet.get("start") or not quiet.get("end"):
        return False
    start, end = _hhmm(quiet["start"]), _hhmm(quiet["end"])
    if start == end:
        return False
    if start < end:
        return start <= at < end
    return at >= start or at < end


def message_text(code: str, side: str, horizon: int, confidence: int) -> str:
    yon = "yükseliş yönlü" if side == "buy" else "satış yönlü"
    return f"{code} · {horizon} günlük ufukta {yon} model sinyali · güven {confidence}"


@dataclass(frozen=True)
class PendingSignal:
    id: int
    user_id: object
    code: str
    side: str
    horizon: int
    confidence: int


@dataclass
class Plan:
    send: list[tuple[PendingSignal, list[str]]] = field(default_factory=list)
    deferred: list[int] = field(default_factory=list)  # sessiz saat → sonra tekrar denenecek
    limited: list[int] = field(default_factory=list)  # gecelik sınır aşıldı → bir daha denenmez
    no_token: list[int] = field(default_factory=list)  # cihaz kaydı yok → sonra tekrar denenebilir


def make_plan(
    pending: list[PendingSignal],
    profiles: dict[object, dict],
    tokens: dict[object, list[str]],
    already_sent: dict[object, int],
    at: time,
) -> Plan:
    plan = Plan()
    by_user: dict[object, list[PendingSignal]] = defaultdict(list)
    for s in pending:
        by_user[s.user_id].append(s)
    for uid, sigs in by_user.items():
        prof = profiles.get(uid, {})
        sigs.sort(key=lambda s: (s.side != "sell", -s.confidence, s.id))
        limit = prof.get("daily_push_limit")
        room = max((DEFAULT_DAILY_LIMIT if limit is None else limit) - already_sent.get(uid, 0), 0)
        sigs, over = sigs[:room], sigs[room:]
        plan.limited += [s.id for s in over]
        if not sigs:
            continue
        if in_quiet_hours(prof.get("quiet_hours"), at):
            plan.deferred += [s.id for s in sigs]
            continue
        toks = [t for t in tokens.get(uid, []) if is_expo_token(t)]
        if not toks:
            plan.no_token += [s.id for s in sigs]
            continue
        plan.send += [(s, toks) for s in sigs]
    return plan


def build_messages(plan: Plan) -> list[tuple[int, str, dict]]:
    """(signal_id, token, Expo mesajı) listesi — her cihaz için ayrı mesaj ki ticket ↔ token eşleşsin."""
    out = []
    for s, toks in plan.send:
        body = f"{message_text(s.code, s.side, s.horizon, s.confidence)}\n{DISCLAIMER}"
        for t in toks:
            out.append(
                (
                    s.id,
                    t,
                    {
                        "to": t,
                        "title": "Yeni model sinyali",
                        "body": body,
                        "data": {"code": s.code, "signal_id": s.id},
                        "sound": "default",
                    },
                )
            )
    return out


def _not_registered(item: dict) -> bool:
    return item.get("status") == "error" and (item.get("details") or {}).get("error") == "DeviceNotRegistered"


# --------------------------------------------------------------------------- veritabanı


def latest_signals_date(conn) -> date | None:
    return conn.execute(
        text("SELECT max(run_date) FROM job_runs WHERE job_name = 'signals' AND status = 'success'")
    ).scalar()


def _previous_pushes(conn, run_date: date) -> tuple[set[int], dict[object, int]]:
    """Bu gece için daha önce gönderilmiş/sınırlanmış sinyaller ve kullanıcı başına gönderilen sayısı."""
    done: set[int] = set()
    sent_ids: set[int] = set()
    for (st,) in conn.execute(
        text("SELECT stats FROM job_runs WHERE job_name = 'push' AND run_date = :rd AND status = 'success'"),
        {"rd": run_date},
    ):
        st = st or {}
        sent_ids.update(st.get("sent_signal_ids", []))
        done.update(st.get("sent_signal_ids", []))
        done.update(st.get("limited_ids", []))
    per_user: dict[object, int] = defaultdict(int)
    if sent_ids:
        for r in conn.execute(
            text(
                "SELECT user_id, count(*) AS n FROM signals WHERE id = ANY(CAST(:ids AS bigint[])) GROUP BY 1"
            ),
            {"ids": sorted(sent_ids)},
        ):
            per_user[r.user_id] = r.n
    return done, per_user


def _pending(conn, run_date: date, done: set[int]) -> list[PendingSignal]:
    rows = conn.execute(
        text(
            f"""
            SELECT id, user_id, code, side, horizon, confidence FROM signals
            WHERE (created_at AT TIME ZONE '{TZ}')::date = CAST(:rd AS date)
            ORDER BY id
            """
        ),
        {"rd": run_date},
    )
    return [
        PendingSignal(r.id, r.user_id, r.code, r.side, r.horizon, r.confidence or 0)
        for r in rows
        if r.id not in done
    ]


def _profiles_and_tokens(conn, user_ids: set) -> tuple[dict, dict]:
    if not user_ids:
        return {}, {}
    ids = [str(u) for u in user_ids]
    profiles = {
        r.user_id: {"quiet_hours": r.quiet_hours, "daily_push_limit": r.daily_push_limit}
        for r in conn.execute(
            text(
                "SELECT user_id, quiet_hours, daily_push_limit FROM profiles "
                "WHERE user_id = ANY(CAST(:ids AS uuid[]))"
            ),
            {"ids": ids},
        )
    }
    tokens: dict = defaultdict(list)
    for r in conn.execute(
        text(
            "SELECT user_id, token FROM push_tokens WHERE user_id = ANY(CAST(:ids AS uuid[])) ORDER BY token"
        ),
        {"ids": ids},
    ):
        tokens[r.user_id].append(r.token)
    return profiles, tokens


def _delete_tokens(conn, tokens: set[str]) -> None:
    if tokens:
        conn.execute(
            text("DELETE FROM push_tokens WHERE token = ANY(CAST(:t AS text[]))"), {"t": sorted(tokens)}
        )


def check_receipts(conn, client: PushClient, now: datetime) -> dict:
    """Önceki push çalıştırmalarının ticket'larını Expo'ya sorar; geçersiz token'ları siler."""
    rows = conn.execute(
        text(
            "SELECT id, stats FROM job_runs WHERE job_name = 'push' AND status = 'success' "
            "AND stats ? 'tickets' AND NOT COALESCE((stats->>'receipts_checked')::boolean, false) "
            "AND finished_at <= CAST(:cutoff AS timestamptz)"
        ),
        {"cutoff": now - RECEIPT_MIN_AGE},
    ).all()
    tickets: dict[str, str] = {}
    for r in rows:
        tickets.update(r.stats.get("tickets") or {})
    result = {"checked": 0, "errors": 0, "removed_tokens": 0}
    if tickets:
        receipts = client.receipts(list(tickets))
        bad = {tickets[tid] for tid, rc in receipts.items() if tid in tickets and _not_registered(rc)}
        _delete_tokens(conn, bad)
        result = {
            "checked": len(receipts),
            "errors": sum(rc.get("status") == "error" for rc in receipts.values()),
            "removed_tokens": len(bad),
        }
    for r in rows:
        conn.execute(
            text(
                "UPDATE job_runs SET stats = stats || jsonb_build_object('receipts_checked', true) "
                "WHERE id = :id"
            ),
            {"id": r.id},
        )
    return result


def run(
    engine: Engine,
    run_date: date | None = None,
    client: PushClient | None = None,
    now: datetime | None = None,
    dry_run: bool = False,
) -> int:
    now = (now or now_tr()).astimezone(TR)
    client = client or ExpoClient()
    with engine.begin() as conn:
        run_date = run_date or latest_signals_date(conn)
        if run_date is None:
            log.info("Henüz başarılı sinyal gecesi yok; gönderilecek bildirim yok")
            return 0
        job_id = (
            None
            if dry_run
            else conn.execute(
                text("INSERT INTO job_runs (job_name, run_date) VALUES ('push', :rd) RETURNING id"),
                {"rd": run_date},
            ).scalar_one()
        )

    try:
        with engine.begin() as conn:
            receipts = {} if dry_run else check_receipts(conn, client, now)
            signal_time = datetime.combine(run_date, SIGNAL_TIME, TR)
            stale = now - signal_time > timedelta(hours=MAX_AGE_HOURS)
            done, per_user = _previous_pushes(conn, run_date)
            pending = [] if stale else _pending(conn, run_date, done)
            profiles, tokens = _profiles_and_tokens(conn, {s.user_id for s in pending})
            plan = make_plan(pending, profiles, tokens, per_user, now.time())
            messages = build_messages(plan)

            tickets: dict[str, str] = {}
            bad: set[str] = set()
            ticket_errors = 0
            if messages and not dry_run:
                result = client.send([m for _, _, m in messages])
                for (_, tok, _), t in zip(messages, result, strict=False):
                    if t.get("status") == "ok" and t.get("id"):
                        tickets[t["id"]] = tok
                    else:
                        ticket_errors += 1
                        if _not_registered(t):
                            bad.add(tok)
                _delete_tokens(conn, bad)

            stats = {
                "run_date": str(run_date),
                "stale": stale,
                "sent_signal_ids": [] if dry_run else sorted({s.id for s, _ in plan.send}),
                "planned_signal_ids": sorted({s.id for s, _ in plan.send}),
                "messages": len(messages),
                "deferred_ids": plan.deferred,
                "limited_ids": [] if dry_run else plan.limited,
                "no_token_ids": plan.no_token,
                "tickets": tickets,
                "ticket_errors": ticket_errors,
                "removed_tokens": len(bad),
                "receipts": receipts,
            }
            if job_id is not None:
                conn.execute(
                    text(
                        "UPDATE job_runs SET finished_at = now(), status = 'success', "
                        "stats = CAST(:st AS jsonb) WHERE id = :id"
                    ),
                    {"st": json.dumps(stats), "id": job_id},
                )
    except Exception as e:
        if job_id is not None:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE job_runs SET finished_at = now(), status = 'failed', error = :e "
                        "WHERE id = :id"
                    ),
                    {"e": repr(e)[:1000], "id": job_id},
                )
        raise

    log.info(
        "push run_date=%s sinyal=%d mesaj=%d ertelenen=%d sınır=%d tokensiz=%d%s%s",
        run_date,
        len(stats["planned_signal_ids"]),
        len(messages),
        len(plan.deferred),
        len(plan.limited),
        len(plan.no_token),
        " [bayat]" if stale else "",
        " [dry-run]" if dry_run else "",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Gece push bildirimi (Expo)")
    p.add_argument("--date", type=date.fromisoformat, help="Sinyal gecesi (varsayılan: son başarılı gece)")
    p.add_argument("--dry-run", action="store_true", help="Gönderme; planı günlüğe yaz")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    url = os.environ.get("DATABASE_URL") and get_settings().database_url  # sürücü öneki düzeltilmiş
    if not url:
        print("DATABASE_URL gerekli", file=sys.stderr)
        return 2
    return run(create_engine(url), args.date, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
