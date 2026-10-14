"""Gece sinyal motoru — run_engine'den hemen sonra (21:30 adımının ikinci yarısı).

    python -m engine.run_signals                 # son analysis gecesi
    python -m engine.run_signals --date 2026-10-13
    python -m engine.run_signals --dry-run

Akış
  1) Ufku dolan açık sinyallerin sonucunu (outcome) doldur — sinyal sicili buna dayanır
  2) Her kullanıcı için engine.signals kurallarıyla yeni alım/satım yönlü model sinyalleri üret
  3) signals tablosuna yaz (created_at = o gecenin 21:30'u, İstanbul saati), job_runs 'signals'

Aynı gece tekrar çalıştırılırsa bekleme süresi kuralı sayesinde çift sinyal oluşmaz.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections import defaultdict
from datetime import date

from sqlalchemy import Engine, create_engine, text

from engine import calibration as cal
from engine import decision as dec
from engine import run_engine
from engine import signals as sig

log = logging.getLogger("engine.signals")
TZ = "Europe/Istanbul"


# --------------------------------------------------------------------------- sonuç doldurma


def fill_outcomes(conn, run_date: date) -> int:
    """outcome'u boş sinyallerden ufku dolanları değerlendirir. Dönüş: doldurulan sinyal sayısı."""
    open_sigs = conn.execute(
        text(
            f"""
            SELECT id, code, side, horizon, (created_at AT TIME ZONE '{TZ}')::date AS d
            FROM signals WHERE outcome IS NULL
            """
        )
    ).all()
    if not open_sigs:
        return 0
    codes = sorted({s.code for s in open_sigs})
    since = min(s.d for s in open_sigs)
    prices = defaultdict(list)
    for r in conn.execute(
        text(
            """
            SELECT code, date, close FROM prices
            WHERE code = ANY(CAST(:codes AS text[])) AND date <= CAST(:rd AS date)
              AND date >= CAST(:since AS date) - 10
            ORDER BY code, date
            """
        ),
        {"codes": codes, "rd": run_date, "since": since},
    ):
        prices[r.code].append((r.date, float(r.close)))

    filled = 0
    for s in open_sigs:
        series = prices.get(s.code, [])
        before = [p for p in series if p[0] <= s.d]
        if not before:
            continue
        entry = before[-1][1]
        after = [p for p in series if p[0] > s.d]
        out = sig.evaluate_outcome(s.side, entry, after, s.horizon)
        if out is None:
            continue
        conn.execute(
            text("UPDATE signals SET outcome = CAST(:o AS jsonb) WHERE id = :id"),
            {"o": json.dumps(out), "id": s.id},
        )
        filled += 1
    return filled


# --------------------------------------------------------------------------- okuma


def load_assets(conn, run_date: date, calibration: dict | None = None) -> dict[str, sig.AssetView]:
    rows = conn.execute(
        text(
            """
            SELECT a.code, s.type, a.horizon, a.direction, a.confidence, a.risk, a.high,
                   (a.indicators->>'atr_pct')::float AS atr_pct, p.close AS price
            FROM analysis a
            JOIN assets s ON s.code = a.code AND s.is_active AND s.type IN ('stock', 'fund')
            JOIN LATERAL (SELECT close FROM prices WHERE code = a.code AND date <= CAST(:rd AS date)
                          ORDER BY date DESC LIMIT 1) p ON true
            WHERE a.run_date = CAST(:rd AS date)
            """
        ),
        {"rd": run_date},
    ).mappings()
    by_code: dict[str, dict] = defaultdict(dict)
    meta: dict[str, tuple[float, float | None]] = {}
    for r in rows:
        by_code[r["code"]][int(r["horizon"])] = {
            "horizon": int(r["horizon"]),
            "direction": r["direction"],
            "confidence": r["confidence"],
            "risk": r["risk"],
            "high": None if r["high"] is None else float(r["high"]),
        }
        meta[r["code"]] = (float(r["price"]), r["atr_pct"], r["type"])
    out = {}
    for c, h in by_code.items():
        price, atr_pct, typ = meta[c]
        allowed = None
        if calibration is not None:
            allowed = frozenset(
                (hz, d) for hz in h for d in ("up", "down") if cal.informative(calibration, typ, hz, d)
            )
        out[c] = sig.AssetView(
            code=c, price=price, atr_pct=atr_pct, by_horizon=h, asset_type=typ, informative=allowed
        )
    return out


def load_users(conn, since: date) -> list[sig.UserView]:
    users = conn.execute(text("SELECT user_id, risk_profile, budget FROM profiles")).all()
    watch = defaultdict(set)
    for r in conn.execute(text("SELECT user_id, code FROM watchlist")):
        watch[r.user_id].add(r.code)
    positions = defaultdict(list)
    for r in conn.execute(
        text(
            """
            SELECT p.id, p.user_id, p.code, p.qty, p.buy_price, s.stop_level
            FROM positions p LEFT JOIN signals s ON s.id = p.signal_id
            WHERE p.sell_date IS NULL
            """
        )
    ):
        positions[r.user_id].append(
            {
                "id": r.id,
                "code": r.code,
                "qty": float(r.qty),
                "buy_price": float(r.buy_price),
                "stop_level": None if r.stop_level is None else float(r.stop_level),
            }
        )
    recent = defaultdict(set)
    for r in conn.execute(
        text(
            f"SELECT user_id, code, side FROM signals WHERE (created_at AT TIME ZONE '{TZ}')::date > :since"
        ),
        {"since": since},
    ):
        recent[r.user_id].add((r.code, r.side))
    return [
        sig.UserView(
            user_id=u.user_id,
            risk_profile=u.risk_profile,
            budget=None if u.budget is None else float(u.budget),
            watchlist=frozenset(watch[u.user_id]),
            open_positions=positions[u.user_id],
            recent=frozenset(recent[u.user_id]),
        )
        for u in users
    ]


# --------------------------------------------------------------------------- yazma


def write_signals(conn, drafts: list[sig.SignalDraft], run_date: date) -> list[int]:
    ids = []
    for d in drafts:
        ids.append(
            conn.execute(
                text(
                    f"""
                    INSERT INTO signals (user_id, code, side, horizon, confidence, suggested_qty, stop_level,
                                         created_at)
                    VALUES (:u, :c, :s, :h, :conf, :q, :stop,
                            (CAST(:rd AS date) + TIME '21:30') AT TIME ZONE '{TZ}')
                    RETURNING id
                    """
                ),
                {
                    "u": d.user_id,
                    "c": d.code,
                    "s": d.side,
                    "h": d.horizon,
                    "conf": d.confidence,
                    "q": d.suggested_qty,
                    "stop": d.stop_level,
                    "rd": run_date,
                },
            ).scalar_one()
        )
    return ids


def run(engine: Engine, run_date: date | None = None, dry_run: bool = False) -> int:
    cfg = dec.load_config()
    t0 = time.monotonic()
    with engine.begin() as conn:
        run_date = run_date or conn.execute(text("SELECT max(run_date) FROM analysis")).scalar()
        if run_date is None:
            log.error("analysis tablosu boş: önce engine.run_engine çalışmalı")
            return 1
        job_id = (
            None
            if dry_run
            else conn.execute(
                text("INSERT INTO job_runs (job_name, run_date) VALUES ('signals', :rd) RETURNING id"),
                {"rd": run_date},
            ).scalar_one()
        )

    try:
        with engine.begin() as conn:
            filled = 0 if dry_run else fill_outcomes(conn, run_date)
            calibration = run_engine.load_calibration(cfg)
            assets = load_assets(conn, run_date, calibration)
            users = load_users(conn, sig.cooldown_since(run_date, cfg))
            drafts = [d for u in users for d in sig.signals_for_user(u, assets, cfg)]
            ids = [] if dry_run else write_signals(conn, drafts, run_date)
            stats = {
                "run_date": str(run_date),
                "users": len(users),
                "assets": len(assets),
                "created": len(drafts),
                "calibration": calibration is not None,
                "buy": sum(d.side == "buy" for d in drafts),
                "sell": sum(d.side == "sell" for d in drafts),
                "sell_reasons": {
                    r: sum(d.reason == r for d in drafts if d.side == "sell")
                    for r in ("model", "stop", "target")
                },
                "outcomes_filled": filled,
                "signal_ids": ids,
                "seconds": round(time.monotonic() - t0, 1),
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
        "run_date=%s kullanıcı=%d sinyal=%d (alım %d, satım %d) sonuç dolduruldu=%d%s",
        run_date,
        stats["users"],
        stats["created"],
        stats["buy"],
        stats["sell"],
        filled,
        " [dry-run]" if dry_run else "",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Gece sinyal motoru → signals tablosu")
    p.add_argument("--date", type=date.fromisoformat)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL gerekli", file=sys.stderr)
        return 2
    return run(create_engine(url), args.date, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
