"""Gece tahmin zinciri (Görev 9) — 20:00, run_daily'den sonra. Kişi 2'nin zamanlayıcısı TEK komut çağırır:

    python -m ml.nightly --db

Sıra: batch_forecast -> model_errors -> scenarios. Her adım ayrı süreçte çalışır (GPU belleği adım
bitince tamamen boşalır, bir adımın çökmesi/takılması zinciri öldürmez).

Sertleştirme:
  * Ön kontrol  : fiyat önbelleği bayatsa (veri işi çalışmamış) tahmin ÜRETİLMEZ, çıkış kodu 1.
  * Kilit       : aynı anda iki zincir çalışmaz (eski kilit 6 saat sonra geçersiz).
  * Zaman aşımı : her adımın üst süresi var; takılan adım öldürülür.
  * Yeniden dene: başarısız adım bir kez daha denenir (geçici DB/ağ hatası için).
  * Bağımlılık  : forecast başarısızsa kalan adımlar atlanır; model_errors başarısızsa senaryolar
                  eşit ağırlıkla üretilir (zincir "partial" biter, çıkış kodu 0).
  * Son kontrol : çıktı dosyaları kurallara göre doğrulanır (120g p50 NULL, p10<=p50<=p90,
                  bear<=base<=bull, kapsama oranı). Kritik ihlal -> çıkış kodu 1.
  * Rapor       : ml/cache/nightly_report_<tarih>.json — Kişi 2 bunu job_runs.stats alanına koyabilir.

Çıkış kodu: 0 = success/partial, 1 = failed.

Kullanım:
    python -m ml.nightly --db
    python -m ml.nightly --codes THYAO GARAN IPB          # hızlı deneme (ön kontrol/kapsama gevşer)
    python -m ml.nightly --skip-model-errors              # yalnızca tahmin + senaryo
    python -m ml.nightly --max-stale-days 9               # uzun bayram tatilinden sonra
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

OUT_DIR = Path(__file__).resolve().parent / "cache"
ROOT = Path(__file__).resolve().parent.parent
LOCK_PATH = OUT_DIR / "nightly.lock"
LOCK_MAX_AGE_S = 6 * 3600
NO_POINT_HORIZONS = {120}


@dataclass(frozen=True)
class Step:
    name: str
    module: str
    critical: bool       # başarısızsa zincir "failed" olur
    timeout_s: int


STEPS = [
    Step("forecast", "ml.batch_forecast", True, 2 * 3600),
    Step("model_errors", "ml.model_errors", False, 90 * 60),
    Step("scenarios", "ml.scenarios", True, 15 * 60),
]


# ---------------------------------------------------------------- kilit

def acquire_lock(path: Path = LOCK_PATH, now: float | None = None, max_age_s: int = LOCK_MAX_AGE_S) -> bool:
    """Kilit alınırsa True. Başka zincir çalışıyorsa (kilit taze) False; eski kilit ezilir."""
    now = time.time() if now is None else now
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            age = now - path.stat().st_mtime
        except OSError:
            age = max_age_s + 1
        if age < max_age_s:
            return False
    path.write_text(f"{os.getpid()} {datetime.now().isoformat(timespec='seconds')}\n", encoding="utf-8")
    return True


def release_lock(path: Path = LOCK_PATH) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------- ön kontrol

def check_freshness(last_dates: dict[str, date | None], today: date, max_stale_days: int = 7,
                    min_fresh_frac: float = 0.5) -> dict:
    """Her varlığın son fiyat tarihine bakar. Varlıkların `min_fresh_frac`'ından azı taze ise ok=False.
    (Hafta sonu/tatil payı için varsayılan 7 gün; uzun bayramda --max-stale-days artırılır.)"""
    known = {c: d for c, d in last_dates.items() if d is not None}
    fresh = [c for c, d in known.items() if (today - d).days <= max_stale_days]
    frac = len(fresh) / len(known) if known else 0.0
    latest = max(known.values()) if known else None
    return {"ok": bool(known) and frac >= min_fresh_frac, "n_assets": len(last_dates),
            "n_with_data": len(known), "fresh_frac": round(frac, 3),
            "latest_price_date": latest.isoformat() if latest else None,
            "max_stale_days": max_stale_days}


def read_last_dates(codes: list[str]) -> dict[str, date | None]:
    from data.collectors.bist_prices import read_cache

    out: dict[str, date | None] = {}
    for c in codes:
        df = read_cache(c)
        out[c] = max(df["date"]) if not df.empty else None
    return out


# ---------------------------------------------------------------- son kontrol

def validate_outputs(forecasts: pd.DataFrame, scenarios: pd.DataFrame | None,
                     n_expected_assets: int, min_asset_frac: float = 0.9) -> tuple[list[str], list[str]]:
    """(kritik_sorunlar, uyarılar). Kritik: sözleşme/kural ihlali; uyarı: eksik kapsama gibi."""
    critical: list[str] = []
    warnings: list[str] = []
    f = forecasts.copy()
    for c in ("p10", "p50", "p90"):
        f[c] = pd.to_numeric(f[c], errors="coerce")

    no_point = f["horizon"].isin(NO_POINT_HORIZONS)
    if f.loc[no_point, "p50"].notna().any():
        critical.append(f"120g satırlarında p50 dolu: {int(f.loc[no_point, 'p50'].notna().sum())} satır (nokta tahmin yok kuralı)")
    if f.loc[~no_point, "p50"].isna().any():
        critical.append(f"p50 boş (120g dışı): {int(f.loc[~no_point, 'p50'].isna().sum())} satır")
    bad_q = f[(f["p10"] > f["p90"]) | (f["p50"] < f["p10"]) | (f["p50"] > f["p90"])]
    if len(bad_q):
        critical.append(f"kantil sırası bozuk (p10<=p50<=p90): {len(bad_q)} satır")
    if (f[["p10", "p90"]] <= 0).any().any():
        critical.append("sıfır/negatif fiyat bandı var")
    if f[["p10", "p90"]].isna().any().any():
        critical.append("p10/p90 boş satır var")

    if n_expected_assets:
        got = f["code"].nunique()
        if got < min_asset_frac * n_expected_assets:
            warnings.append(f"tahmin üretilen varlık az: {got}/{n_expected_assets}")

    if scenarios is None:
        critical.append("scenarios çıktısı yok")
    else:
        s = scenarios
        if s.empty:
            critical.append("scenarios boş")
        else:
            bad = s[~((s["bear"] <= s["base"]) & (s["base"] <= s["bull"]))]
            if len(bad):
                critical.append(f"senaryo sırası bozuk (bear<=base<=bull): {len(bad)} satır")
            if n_expected_assets and s["code"].nunique() < min_asset_frac * n_expected_assets:
                warnings.append(f"senaryosu olan varlık az: {s['code'].nunique()}/{n_expected_assets}")
    return critical, warnings


# ---------------------------------------------------------------- adım çalıştırma

def run_subprocess(cmd: list[str], timeout_s: int, tail_lines: int = 30) -> tuple[int, list[str]]:
    """Çıktıyı canlı ekrana yansıtır, son satırları döndürür. Zaman aşımında süreç öldürülür (rc=124)."""
    tail: collections.deque[str] = collections.deque(maxlen=tail_lines)
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace")
    deadline = time.time() + timeout_s
    import threading

    def pump() -> None:
        for line in proc.stdout:  # type: ignore[union-attr]
            sys.stdout.write(line)
            tail.append(line.rstrip())

    t = threading.Thread(target=pump, daemon=True)
    t.start()
    while t.is_alive() and time.time() < deadline:
        t.join(timeout=1.0)
    if t.is_alive():
        proc.kill()
        proc.wait()
        tail.append(f"ZAMAN AŞIMI: {timeout_s} sn")
        return 124, list(tail)
    return proc.wait(), list(tail)


def run_step(step: Step, args: list[str], runner=run_subprocess, retries: int = 1,
             sleep=time.sleep, retry_wait_s: int = 30) -> dict:
    cmd = [sys.executable, "-m", step.module, *args]
    t0 = time.time()
    attempts = 0
    rc, tail = 1, []
    while attempts <= retries:
        attempts += 1
        print(f"\n===== {step.name} (deneme {attempts}) =====", flush=True)
        rc, tail = runner(cmd, step.timeout_s)
        if rc == 0:
            break
        if rc == 124 or attempts > retries:   # zaman aşımı tekrar denenmez (saatleri yer)
            break
        print(f"{step.name} başarısız (kod {rc}); {retry_wait_s} sn sonra tekrar denenecek", file=sys.stderr)
        sleep(retry_wait_s)
    return {"name": step.name, "status": "success" if rc == 0 else "failed", "returncode": rc,
            "attempts": attempts, "duration_s": round(time.time() - t0, 1),
            "critical": step.critical, "tail": [] if rc == 0 else tail[-10:]}


# ---------------------------------------------------------------- zincir

def orchestrate(run_date: date, db: bool, codes: list[str] | None, skip_model_errors: bool,
                runner=run_subprocess, sleep=time.sleep, retry_wait_s: int = 30,
                out_dir: Path = OUT_DIR, forecast_models: list[str] | None = None) -> dict:
    """Adımları sırayla çalıştırır. Dönüş: rapor sözlüğü (status: success | partial | failed)."""
    iso = run_date.isoformat()
    common = (["--db"] if db else [])
    scope = (["--codes", *codes] if codes else [])
    f_csv = out_dir / f"forecasts_{iso}.csv"
    e_csv = out_dir / f"model_errors_{iso}.csv"

    arg_map = {
        "forecast": [*common, *scope, "--run-date", iso,
                     *(["--models", *forecast_models] if forecast_models else [])],
        "model_errors": [*common, *scope],
        "scenarios": [*common, "--forecasts", str(f_csv), "--errors", str(e_csv)],
    }
    steps: list[dict] = []
    forecast_ok = True
    for step in STEPS:
        if step.name == "model_errors" and skip_model_errors:
            steps.append({"name": step.name, "status": "skipped", "critical": False})
            continue
        if step.name != "forecast" and not forecast_ok:
            steps.append({"name": step.name, "status": "skipped", "critical": step.critical,
                          "reason": "forecast başarısız"})
            continue
        res = run_step(step, arg_map[step.name], runner, sleep=sleep, retry_wait_s=retry_wait_s)
        steps.append(res)
        if step.name == "forecast" and res["status"] != "success":
            forecast_ok = False

    failed_critical = [s["name"] for s in steps if s["status"] == "failed" and s["critical"]]
    failed_soft = [s["name"] for s in steps if s["status"] == "failed" and not s["critical"]]
    status = "failed" if failed_critical else ("partial" if failed_soft else "success")
    return {"run_date": iso, "db": db, "status": status, "steps": steps,
            "failed_critical": failed_critical, "failed_soft": failed_soft}


def read_csv_or_none(path: Path) -> pd.DataFrame | None:
    return pd.read_csv(path) if path.exists() else None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Gece tahmin zinciri (20:00): forecast -> model_errors -> scenarios")
    p.add_argument("--db", action="store_true", help="tablolara yaz (DATABASE_URL gerekir)")
    p.add_argument("--codes", nargs="*", help="Yalnızca bu varlıklar (deneme)")
    p.add_argument("--run-date", help="YYYY-MM-DD (varsayılan: bugün)")
    p.add_argument("--skip-model-errors", action="store_true")
    p.add_argument("--max-stale-days", type=int, default=7, help="Fiyat verisi en çok kaç gün eski olabilir")
    p.add_argument("--skip-freshness", action="store_true", help="Ön kontrolü atla")
    args = p.parse_args(argv)

    t0 = time.time()
    run_date = date.fromisoformat(args.run_date) if args.run_date else date.today()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUT_DIR / f"nightly_report_{run_date.isoformat()}.json"

    def finish(report: dict, code: int) -> int:
        report["duration_s"] = round(time.time() - t0, 1)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"\n== Gece zinciri: {report['status'].upper()} ({report['duration_s']} sn) -> {report_path}")
        for key in ("problems", "warnings"):
            for line in report.get(key, []):
                print(f"  [{key}] {line}", file=sys.stderr if key == "problems" else sys.stdout)
        return code

    if args.db and not os.environ.get("DATABASE_URL"):
        print("--db için DATABASE_URL gerekli", file=sys.stderr)
        return 1
    if not acquire_lock():
        print(f"Başka bir gece zinciri çalışıyor ({LOCK_PATH}); çıkılıyor.", file=sys.stderr)
        return 1
    try:
        from ml.batch_forecast import load_universe_codes

        universe = load_universe_codes(args.codes)
        codes = universe["code"].tolist()

        freshness = None
        if not args.skip_freshness:
            freshness = check_freshness(read_last_dates(codes), date.today(), args.max_stale_days)
            print(f"Veri tazeliği: son fiyat {freshness['latest_price_date']}, taze oran {freshness['fresh_frac']:.0%}")
            if not freshness["ok"]:
                return finish({"run_date": run_date.isoformat(), "status": "failed", "freshness": freshness,
                               "steps": [], "problems": ["fiyat verisi bayat; önce: python -m data.run_daily"]}, 1)

        from ml.models.base import load_config

        fmodels = load_config().get("nightly", {}).get("forecast_models")   # boşsa config'teki tüm modeller
        report = orchestrate(run_date, args.db, args.codes, args.skip_model_errors, forecast_models=fmodels)
        report["freshness"] = freshness

        iso = run_date.isoformat()
        f = read_csv_or_none(OUT_DIR / f"forecasts_{iso}.csv")
        s = read_csv_or_none(OUT_DIR / f"scenarios_{date.today().isoformat()}.csv")  # scenarios.py dosyayı bugünün tarihiyle yazar
        problems: list[str] = []
        warnings: list[str] = []
        if report["status"] != "failed" and f is not None:
            problems, warnings = validate_outputs(f, s, len(codes))
        elif report["status"] != "failed":
            problems = ["forecasts çıktısı yok"]
        if report["failed_soft"]:
            warnings.append(f"{', '.join(report['failed_soft'])} başarısız: senaryolar eşit ağırlıkla üretildi")
        report["problems"], report["warnings"] = problems, warnings
        if problems:
            report["status"] = "failed"
        return finish(report, 1 if report["status"] == "failed" else 0)
    finally:
        release_lock()


if __name__ == "__main__":
    sys.exit(main())
