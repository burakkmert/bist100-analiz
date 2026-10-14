"""Gece karar motoru (21:30) — Kişi 1'in tahmin zinciri (ml.nightly) bittikten sonra çalışır.

    python -m engine.run_engine                      # son tahmin gecesi için tüm varlıklar
    python -m engine.run_engine --date 2026-10-13    # belirli gece
    python -m engine.run_engine --codes THYAO IPB    # hızlı deneme
    python -m engine.run_engine --dry-run            # hesapla, veritabanına yazma

Akış
  1) run_date = forecasts tablosundaki en son gece (ya da --date)
  2) Okunanlar (yalnızca run_date ve öncesi; veri sızıntısı yok):
       assets (aktif hisse + fon), prices (son ~2 yıl), forecasts (run_date, ensemble modelleri, 1/5/20 gün),
       model_errors (her model × ufuk için run_date'ten önceki en güncel kayıt, 60 günlük pencere),
       XU100 fiyatları (piyasa geneli rejim → her satırın indicators.market_regime alanı)
  3) Her varlık için engine.decision.analyze → analysis satırları
  4) analysis tablosuna upsert (aynı gece yeniden çalıştırılabilir)
  5) job_runs: 'engine' kaydı (başlangıç, bitiş, durum, istatistik)

Çıkış kodu: 0 = başarılı; 1 = hiç satır yazılamadı ya da varlıkların %10'undan fazlasında hata.
Bir varlıktaki hata diğerlerini durdurmaz; hatalı kodlar job_runs.stats'a yazılır.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import Engine, create_engine, text

from engine import calibration as cal
from engine import decision as dec
from engine import regime as reg

log = logging.getLogger("engine")

MARKET_INDEX = "XU100"
PRICE_LOOKBACK_DAYS = 800  # ~2 yıl takvim günü: 1 yıllık volatilite yüzdeliği + MA50 için yeterli
MIN_PRICE_ROWS = 60  # bundan kısa geçmişte analiz üretilmez
MAX_FAIL_FRAC = 0.10

NUMERIC = ["open", "high", "low", "close", "adj_close", "volume"]


# --------------------------------------------------------------------------- okuma


def latest_run_date(conn) -> date | None:
    return conn.execute(text("SELECT max(run_date) FROM forecasts")).scalar()


def load_assets(conn, codes: list[str] | None) -> dict[str, str]:
    rows = conn.execute(
        text(
            "SELECT code, type FROM assets WHERE is_active AND type IN ('stock', 'fund') "
            "AND (CAST(:codes AS text[]) IS NULL OR code = ANY(CAST(:codes AS text[]))) ORDER BY code"
        ),
        {"codes": codes},
    ).all()
    return {r.code: r.type for r in rows}


def load_prices(conn, codes: list[str], run_date: date) -> pd.DataFrame:
    rows = conn.execute(
        text(
            """
            SELECT code, date, open, high, low, close, adj_close, volume FROM prices
            WHERE code = ANY(CAST(:codes AS text[]))
              AND date <= CAST(:rd AS date) AND date > CAST(:since AS date)
            ORDER BY code, date
            """
        ),
        {"codes": codes, "rd": run_date, "since": run_date - timedelta(days=PRICE_LOOKBACK_DAYS)},
    ).mappings()
    df = pd.DataFrame(list(rows), columns=["code", "date", *NUMERIC])
    for c in NUMERIC:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    return df


def load_forecasts(conn, run_date: date, models: list[str], horizons: list[int]) -> pd.DataFrame:
    rows = conn.execute(
        text(
            """
            SELECT code, model, horizon, p10, p50, p90 FROM forecasts
            WHERE run_date = CAST(:rd AS date)
              AND model = ANY(CAST(:models AS text[]))
              AND horizon = ANY(CAST(:hs AS smallint[]))
            """
        ),
        {"rd": run_date, "models": models, "hs": horizons},
    ).mappings()
    df = pd.DataFrame(list(rows), columns=["code", "model", "horizon", "p10", "p50", "p90"])
    for c in ("p10", "p50", "p90"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    return df


def load_errors(conn, run_date: date, models: list[str], window_days: int) -> pd.DataFrame:
    """Her (varlık, model, ufuk) için run_date'ten ÖNCEKİ en güncel MAE (sonraki kayıt kullanılmaz)."""
    rows = conn.execute(
        text(
            """
            SELECT DISTINCT ON (code, model, horizon) code, model, horizon, mae
            FROM model_errors
            WHERE window_days = CAST(:w AS smallint) AND as_of <= CAST(:rd AS date)
              AND model = ANY(CAST(:models AS text[]))
            ORDER BY code, model, horizon, as_of DESC
            """
        ),
        {"w": window_days, "rd": run_date, "models": models},
    ).mappings()
    df = pd.DataFrame(list(rows), columns=["code", "model", "horizon", "mae"])
    df["mae"] = pd.to_numeric(df["mae"], errors="coerce").astype(float)
    return df


# --------------------------------------------------------------------------- saf hesap (test edilebilir)


def _none_if_nan(x: Any) -> float | None:
    return None if x is None or pd.isna(x) else float(x)


def group_forecasts(fc: pd.DataFrame) -> dict[str, dict[int, dict[str, tuple]]]:
    """{kod: {ufuk: {model: (p10, p50, p90)}}}"""
    out: dict = defaultdict(lambda: defaultdict(dict))
    for r in fc.itertuples(index=False):
        out[r.code][int(r.horizon)][r.model] = (
            _none_if_nan(r.p10),
            _none_if_nan(r.p50),
            _none_if_nan(r.p90),
        )
    return out


def group_errors(err: pd.DataFrame) -> dict[str, dict[int, dict[str, float | None]]]:
    """{kod: {ufuk: {model: mae}}}"""
    out: dict = defaultdict(lambda: defaultdict(dict))
    for r in err.itertuples(index=False):
        out[r.code][int(r.horizon)][r.model] = _none_if_nan(r.mae)
    return out


def market_regime(prices: pd.DataFrame, cfg: dict) -> str | None:
    px = prices[prices["code"] == MARKET_INDEX].set_index("date")
    if len(px) < MIN_PRICE_ROWS:
        return None
    return reg.classify(px.drop(columns="code"), cfg.get("regime")).name


def db_url(url: str) -> str:
    """Supabase/Render "postgresql://" metnini psycopg (3) sürücüsüne çevirir (psycopg2 kurulu değil)."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


def load_calibration(cfg: dict) -> dict | None:
    """config.yaml 'calibration' bölümü; dosya yoksa ya da kapalıysa None (ham puanlar kullanılır)."""
    c = cfg.get("calibration") or {}
    if not c.get("enabled", True):
        return None
    path = c.get("path")
    mapping = cal.load(cal.REPO_DIR / path if path else None)
    if mapping is None:
        log.info("Güven eşlemesi bulunamadı; kalibrasyonsuz devam ediliyor")
    return mapping


def analyze_all(
    run_date: date,
    assets: dict[str, str],
    prices: pd.DataFrame,
    fc: pd.DataFrame,
    err: pd.DataFrame,
    cfg: dict,
    calibration: dict | None = None,
) -> tuple[list[dict], dict]:
    """Tüm varlıklar için analysis satırları ve istatistik. Bir varlığın hatası diğerlerini durdurmaz."""
    fcs, errs = group_forecasts(fc), group_errors(err)
    market = market_regime(prices, cfg)
    by_code = {c: g.drop(columns="code").set_index("date") for c, g in prices.groupby("code", sort=False)}

    rows: list[dict] = []
    stats: dict = {
        "run_date": str(run_date),
        "assets": len(assets),
        "ok": 0,
        "skipped_no_forecast": 0,
        "skipped_short_history": 0,
        "failed": [],
        "market_regime": market,
        "calibration": calibration is not None,
    }
    for code, asset_type in assets.items():
        if code not in fcs:
            stats["skipped_no_forecast"] += 1
            continue
        px = by_code.get(code)
        if px is None or len(px) < MIN_PRICE_ROWS:
            stats["skipped_short_history"] += 1
            continue
        try:
            out = dec.analyze(code, run_date, px, fcs[code], errs.get(code, {}), cfg, asset_type, calibration)
        except Exception as e:  # noqa: BLE001 — tek varlık zinciri durdurmasın
            log.warning("%s analiz edilemedi: %r", code, e)
            stats["failed"].append({"code": code, "error": repr(e)[:200]})
            continue
        for r in out:
            r["indicators"]["market_regime"] = market
        rows.extend(out)
        stats["ok"] += 1
    stats["rows"] = len(rows)
    stats["directions"] = {d: sum(1 for r in rows if r["direction"] == d) for d in ("up", "down", "flat")}
    return rows, stats


def is_failure(stats: dict) -> bool:
    attempted = stats["ok"] + len(stats["failed"])
    if stats["rows"] == 0:
        return True
    return attempted > 0 and len(stats["failed"]) / attempted > MAX_FAIL_FRAC


# --------------------------------------------------------------------------- yazma


_UPSERT = text(
    """
    INSERT INTO analysis (code, run_date, horizon, direction, confidence, risk, regime,
                          weights, indicators, low, mid, high)
    VALUES (:code, :run_date, :horizon, :direction, :confidence, :risk, :regime,
            CAST(:weights AS jsonb), CAST(:indicators AS jsonb), :low, :mid, :high)
    ON CONFLICT (code, run_date, horizon) DO UPDATE SET
        direction = EXCLUDED.direction, confidence = EXCLUDED.confidence, risk = EXCLUDED.risk,
        regime = EXCLUDED.regime, weights = EXCLUDED.weights, indicators = EXCLUDED.indicators,
        low = EXCLUDED.low, mid = EXCLUDED.mid, high = EXCLUDED.high
    """
)


def write_analysis(conn, rows: list[dict], chunk: int = 1000) -> int:
    payload = [
        {
            **r,
            "weights": json.dumps(r["weights"], ensure_ascii=False),
            "indicators": json.dumps(r["indicators"], ensure_ascii=False, default=str),
        }
        for r in rows
    ]
    for i in range(0, len(payload), chunk):
        conn.execute(_UPSERT, payload[i : i + chunk])
    return len(payload)


def job_start(conn, run_date: date) -> int:
    return conn.execute(
        text("INSERT INTO job_runs (job_name, run_date) VALUES ('engine', :rd) RETURNING id"),
        {"rd": run_date},
    ).scalar_one()


def job_finish(conn, job_id: int, status: str, stats: dict, error: str | None = None) -> None:
    conn.execute(
        text(
            "UPDATE job_runs SET finished_at = now(), status = :s, error = :e, "
            "stats = CAST(:st AS jsonb) WHERE id = :id"
        ),
        {"s": status, "e": error, "st": json.dumps(stats, ensure_ascii=False, default=str), "id": job_id},
    )


# --------------------------------------------------------------------------- giriş noktası


def run(
    engine: Engine, run_date: date | None = None, codes: list[str] | None = None, dry_run: bool = False
) -> int:
    cfg = dec.load_config()
    models = cfg["ensemble"]["models"]
    horizons = cfg["signals"]["horizons"]
    t0 = time.monotonic()

    with engine.connect() as conn:
        run_date = run_date or latest_run_date(conn)
        if run_date is None:
            log.error("forecasts tablosu boş: önce Kişi 1'in gece zinciri (ml.nightly --db) çalışmalı")
            return 1
        assets = load_assets(conn, codes)
        prices = load_prices(conn, [*assets, MARKET_INDEX], run_date)
        fc = load_forecasts(conn, run_date, models, horizons)
        err = load_errors(conn, run_date, models, cfg["ensemble"]["error_window_days"])

    job_id = None
    if not dry_run:
        with engine.begin() as conn:
            job_id = job_start(conn, run_date)

    try:
        rows, stats = analyze_all(run_date, assets, prices, fc, err, cfg, load_calibration(cfg))
        stats["seconds"] = round(time.monotonic() - t0, 1)
        failed = is_failure(stats)
        if not dry_run:
            with engine.begin() as conn:
                write_analysis(conn, rows)
                job_finish(conn, job_id, "failed" if failed else "success", stats)
    except Exception as e:
        if job_id is not None:
            with engine.begin() as conn:
                job_finish(conn, job_id, "failed", {"run_date": str(run_date)}, repr(e)[:1000])
        raise

    log.info(
        "run_date=%s varlık=%d başarılı=%d satır=%d hatalı=%d tahminsiz=%d kısa=%d piyasa=%s (%.1f sn)%s",
        run_date,
        stats["assets"],
        stats["ok"],
        stats["rows"],
        len(stats["failed"]),
        stats["skipped_no_forecast"],
        stats["skipped_short_history"],
        stats["market_regime"],
        stats["seconds"],
        " [dry-run: yazılmadı]" if dry_run else "",
    )
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Gece karar motoru → analysis tablosu")
    p.add_argument("--date", type=date.fromisoformat, help="Tahmin gecesi (varsayılan: en sonuncusu)")
    p.add_argument("--codes", nargs="+", help="Yalnızca bu varlıklar")
    p.add_argument("--dry-run", action="store_true", help="Hesapla ama veritabanına yazma")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL ortam değişkeni gerekli (.env'deki gibi)", file=sys.stderr)
        return 2
    codes = [c.upper() for c in args.codes] if args.codes else None
    return run(create_engine(db_url(url)), args.date, codes, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
