"""TEFAS günlük fon fiyatı toplayıcı (Görev 2) — tefasmak.

- İlk yükleme: önbelleği boş olan her fon için tek istekle 5 yıllık seri (fon_5y_fiyat).
- Artımlı güncelleme: önbelleği dolu fonların eksik günleri TEK bir toplu çağrıyla
  (fonlar_gunluk_detay_aralik) çekilir; 300 fon için birkaç istek yeter.
- Hız sınırı (~6 istek/dk), 429 ve tekrar deneme tefasmak içinde yönetilir; bir fon
  hata verirse diğerleri devam eder.
- Önbellek biçimi BIST ile aynıdır (data/cache/prices/<KOD>.csv); fonlarda yalnızca
  close (= adj_close) dolu, OHLV boş.

Kullanım:
    python -m data.collectors.tefas_list                  # önce fon evreni
    python -m data.collectors.tefas_prices                # evrendeki tüm fonlar
    python -m data.collectors.tefas_prices --codes IPB TTE
    python -m data.collectors.tefas_prices --db           # ayrıca prices tablosuna yaz
"""
from __future__ import annotations

import argparse
import os
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from data.collectors.bist_prices import (
    CACHE_DIR, PRICE_COLUMNS, merge_prices, read_cache, upsert_prices_db, write_cache,
)
from data.collectors.tefas_list import load_fund_list

REFETCH_DAYS = 3  # son günleri yeniden çek: TEFAS fiyatı bazen geç düzeltilir


# ---------------------------------------------------------------- dönüştürme

def parse_tefas_date(value) -> date:
    """TEFAS tarihleri: epoch ms, '2026-10-07' veya '07.10.2026' gelebilir."""
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        return pd.to_datetime(int(value), unit="ms").date()
    s = str(value)
    return pd.to_datetime(s, dayfirst="." in s).date()


def normalize_tefas_rows(rows: list[dict], code: str | None = None) -> pd.DataFrame:
    """tefasmak satırlarını `prices` biçimine çevirir.
    code verilmezse her satırdaki fonKodu kullanılır (toplu çağrılar)."""
    records = []
    for r in rows or []:
        fund = (code or r.get("fonKodu") or r.get("kod") or "").strip().upper()
        price = r.get("fiyat", r.get("sonFiyat"))
        when = r.get("tarih")
        if not fund or price in (None, "") or when in (None, ""):
            continue
        price = float(str(price).replace(",", ".")) if isinstance(price, str) else float(price)
        if price <= 0:          # sıfır/negatif fiyat: temizleme adımı raporlar, burada atla
            continue
        records.append({
            "code": fund, "date": parse_tefas_date(when),
            "open": None, "high": None, "low": None,
            "close": price, "adj_close": price, "volume": None,
        })
    df = pd.DataFrame(records, columns=PRICE_COLUMNS)
    return df.drop_duplicates(["code", "date"], keep="last").sort_values(["code", "date"]).reset_index(drop=True)


# ---------------------------------------------------------------- indirme

def fetch_full_history(code: str) -> pd.DataFrame:
    import tefasmak as tf

    return normalize_tefas_rows(tf.fon_5y_fiyat(code), code)


def fetch_range_bulk(start: date, end: date, fund_type: str = "YAT") -> pd.DataFrame:
    import tefasmak as tf

    rows = tf.fonlar_gunluk_detay_aralik(
        fon_tipi=fund_type, bas_tarih=start.strftime("%Y%m%d"), bit_tarih=end.strftime("%Y%m%d"),
    )
    return normalize_tefas_rows(rows)


# ---------------------------------------------------------------- iş akışı

def run(codes: list[str], cache_dir: Path = CACHE_DIR, today: date | None = None,
        full_fetch=fetch_full_history, bulk_fetch=fetch_range_bulk) -> pd.DataFrame:
    today = today or date.today()
    existing = {c: read_cache(c, cache_dir) for c in codes}
    new_codes = [c for c in codes if existing[c].empty]
    old_codes = [c for c in codes if not existing[c].empty]
    report = {}

    # 1) İlk yükleme: fon başına bir istek
    for i, code in enumerate(new_codes, 1):
        try:
            df = full_fetch(code)
            if df.empty:
                raise ValueError("veri yok")
            write_cache(df, code, cache_dir)
            report[code] = {"new_rows": len(df), "total_rows": len(df), "error": None}
        except Exception as exc:
            report[code] = {"new_rows": 0, "total_rows": 0, "error": str(exc)}
        print(f"[ilk {i}/{len(new_codes)}] {code}: "
              + (report[code]["error"] or f"+{report[code]['new_rows']} satır"))

    # 2) Artımlı: tüm eski fonlar için tek toplu çağrı
    if old_codes:
        start = min(max(existing[c]["date"]) for c in old_codes) - timedelta(days=REFETCH_DAYS)
        try:
            bulk = bulk_fetch(start, today)
            bulk_error = None
        except Exception as exc:
            bulk, bulk_error = pd.DataFrame(columns=PRICE_COLUMNS), str(exc)
        for code in old_codes:
            if bulk_error:
                report[code] = {"new_rows": 0, "total_rows": len(existing[code]), "error": bulk_error}
                continue
            merged = merge_prices(existing[code], bulk[bulk["code"] == code])
            write_cache(merged, code, cache_dir)
            report[code] = {"new_rows": len(merged) - len(existing[code]),
                            "total_rows": len(merged), "error": None}
        print(f"[artımlı] {len(old_codes)} fon, {start} → {today}"
              + (f"  HATA: {bulk_error}" if bulk_error else ""))

    return pd.DataFrame([{"code": c, **report[c]} for c in codes])


def main() -> None:
    parser = argparse.ArgumentParser(description="TEFAS fon fiyatı toplayıcı")
    parser.add_argument("--codes", nargs="*", help="Boşsa tefas_funds.csv'deki evren")
    parser.add_argument("--db", action="store_true", help="DATABASE_URL'deki prices tablosuna da yaz")
    args = parser.parse_args()

    codes = [c.upper() for c in args.codes] if args.codes else load_fund_list()["code"].tolist()
    report = run(codes)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    report.to_csv(CACHE_DIR / "_report_tefas.csv", index=False)

    if args.db:
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise SystemExit("--db için DATABASE_URL ortam değişkeni gerekli")
        ok = report.loc[report["error"].isna(), "code"]
        frames = [read_cache(c) for c in ok]
        n = upsert_prices_db(pd.concat(frames, ignore_index=True), url) if frames else 0
        print(f"DB: {n} satır upsert edildi")

    errors = report.loc[report["error"].notna(), "code"].tolist()
    print(f"\nBitti. {len(report) - len(errors)}/{len(report)} başarılı. Hatalı: {errors or 'yok'}")


if __name__ == "__main__":
    main()
