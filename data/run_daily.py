"""Gece veri işi giriş noktası (19:00) — Kişi 2'nin zamanlayıcısı bunu çağırır.

Adımlar:
  1) BIST hisseleri + XU100 endeksi (yfinance, artımlı)
  2) TEFAS fonları (tefasmak; evren listesi yoksa önce oluşturulur)
  3) Temizleme + doğrulama -> data/cache/reports/quality_<tarih>.json
  4) --db verilirse: assets ve prices tablolarına upsert

Çıkış kodu: hatalı varlık oranı --max-error-rate'i aşarsa 1 (job_runs 'failed' olsun diye), yoksa 0.

Kullanım:
    python -m data.run_daily                         # tam gece işi
    python -m data.run_daily --stocks THYAO GARAN --funds IPB   # hızlı deneme
    python -m data.run_daily --skip-collect          # yalnızca temizle + raporla
    python -m data.run_daily --db                    # DATABASE_URL'e de yaz
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import pandas as pd

from data.collectors import bist_prices, tefas_prices
from data.collectors.bist_list import load_stock_list
from data.collectors.bist_prices import INDEX_CODE, read_cache, write_cache
from data.collectors.tefas_list import FUNDS_CSV, fetch_fund_universe, load_fund_list
from data.cleaning import adjust_jumps, market_calendar
from data.validate import build_report, validate_assets, write_report


def load_universe(stock_codes: list[str] | None, fund_codes: list[str] | None) -> pd.DataFrame:
    """assets biçiminde evren: hisseler (CSV) + fonlar (tefas_funds.csv, yoksa TEFAS'tan)."""
    stocks = load_stock_list()
    if stock_codes is not None:
        stocks = stocks[stocks["code"].isin(stock_codes)]
    if fund_codes is not None:
        funds = pd.DataFrame({"code": fund_codes, "name": fund_codes, "type": "fund",
                              "sector": None, "is_active": True, "min_history_ok": False})
    else:
        if not FUNDS_CSV.exists():
            fetch_fund_universe().to_csv(FUNDS_CSV, index=False)
        funds = load_fund_list().assign(type="fund")
    cols = ["code", "name", "type", "sector", "is_active", "min_history_ok"]
    return pd.concat([stocks[cols], funds[cols]], ignore_index=True)


def upsert_assets_db(assets: pd.DataFrame, database_url: str) -> int:
    from sqlalchemy import MetaData, Table, create_engine
    from sqlalchemy.dialects.postgresql import insert

    engine = create_engine(database_url)
    table = Table("assets", MetaData(), autoload_with=engine)
    clean = assets.astype(object)
    records = clean.where(clean.notna(), None).to_dict("records")
    with engine.begin() as conn:
        stmt = insert(table).values(records)
        conn.execute(stmt.on_conflict_do_update(
            index_elements=["code"],
            set_={c: stmt.excluded[c] for c in ("name", "type", "sector", "is_active", "min_history_ok")},
        ))
    return len(records)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Gece veri işi (19:00)")
    p.add_argument("--stocks", nargs="*", help="Yalnızca bu hisseler (deneme)")
    p.add_argument("--funds", nargs="*", help="Yalnızca bu fonlar (deneme)")
    p.add_argument("--skip-collect", action="store_true", help="Veri çekme; yalnızca temizle + raporla")
    p.add_argument("--db", action="store_true", help="assets + prices tablolarına yaz")
    p.add_argument("--max-error-rate", type=float, default=0.2)
    args = p.parse_args(argv)

    t0 = time.time()
    stock_codes = [c.upper() for c in args.stocks] if args.stocks is not None else None
    fund_codes = [c.upper() for c in args.funds] if args.funds is not None else None
    if (stock_codes is None) != (fund_codes is None):  # biri verildiyse diğeri boş sayılır
        stock_codes, fund_codes = stock_codes or [], fund_codes or []
    universe = load_universe(stock_codes, fund_codes)
    types = dict(zip(universe["code"], universe["type"]))
    stocks = [c for c, t in types.items() if t == "stock"]
    funds = [c for c, t in types.items() if t == "fund"]

    errors: list[str] = []
    if not args.skip_collect:
        print(f"== 1) BIST: {len(stocks)} hisse + {INDEX_CODE}")
        rep = bist_prices.run(stocks + [INDEX_CODE], years=5)
        errors += rep.loc[rep["error"].notna(), "code"].tolist()
        if funds:
            print(f"== 2) TEFAS: {len(funds)} fon")
            rep = tefas_prices.run(funds)
            errors += rep.loc[rep["error"].notna(), "code"].tolist()

    print("== 3) Temizleme + doğrulama")
    frames = {c: read_cache(c) for c in universe["code"]}
    cleaned, summary, issues = validate_assets(frames, types)
    for code, df in cleaned.items():
        if not df.empty and len(df) != len(frames[code]):
            write_cache(df, code)  # sıfır/negatif ve çift kayıtlar önbellekten de temizlenir
    report = build_report(summary, errors)
    report["duration_s"] = round(time.time() - t0, 1)
    path = write_report(report, summary, issues)

    if args.db:
        url = os.environ.get("DATABASE_URL")
        if not url:
            print("--db için DATABASE_URL gerekli", file=sys.stderr)
            return 1
        print("== 4) Veritabanı")
        ok = summary.set_index("code")["min_history_ok"]
        assets = universe.assign(min_history_ok=universe["code"].map(ok).fillna(False))
        print(f"assets: {upsert_assets_db(assets, url)} satır")
        stock_cal = market_calendar([df for c, df in cleaned.items() if types.get(c) == "stock"])
        adjusted = [adjust_jumps(df, types.get(c, "stock"), stock_cal if types.get(c) == "stock" else None)
                    for c, df in cleaned.items() if not df.empty]
        prices = pd.concat(adjusted, ignore_index=True)  # adj_close: bedelsiz/hata düzeltilmiş
        print(f"prices: {bist_prices.upsert_prices_db(prices, url)} satır")

    # Uzun listeler ekranda kısaltılır; tamamı JSON dosyasında
    shown = {k: (v if not isinstance(v, list) or len(v) <= 10 else f"{len(v)} varlık: {', '.join(v[:10])} ...")
             for k, v in report.items()}
    print(json.dumps(shown, ensure_ascii=False, indent=2, default=str))
    print(f"Rapor: {path}")

    error_rate = len(errors) / max(1, len(universe))
    if len(universe) == 0 or error_rate > args.max_error_rate:
        print(f"BAŞARISIZ: hata oranı %{error_rate * 100:.1f}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
