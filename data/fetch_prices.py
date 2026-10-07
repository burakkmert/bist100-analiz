"""BIST100 hisselerinin günlük fiyat verisini yfinance ile çeker.

Kullanım:
    python data/fetch_prices.py --years 5
    python data/fetch_prices.py --symbols THYAO GARAN --years 2

Çıktı: data/raw/<SEMBOL>.parquet  (Date, Open, High, Low, Close, Adj Close, Volume)
Ayrıca data/raw/_report.csv dosyasına her hisse için satır sayısı ve eksik gün özeti yazılır.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent
SYMBOLS_FILE = ROOT / "bist100_symbols.csv"
RAW_DIR = ROOT / "raw"
INDEX_TICKER = "XU100.IS"  # BIST100 endeksi, bağlam serisi olarak


def load_symbols() -> list[str]:
    return pd.read_csv(SYMBOLS_FILE)["symbol"].str.strip().str.upper().tolist()


def fetch_one(symbol: str, start: date) -> pd.DataFrame:
    ticker = symbol if symbol.endswith(".IS") else f"{symbol}.IS"
    df = yf.download(ticker, start=start.isoformat(), auto_adjust=False, progress=False)
    if isinstance(df.columns, pd.MultiIndex):  # yeni yfinance sürümleri
        df.columns = df.columns.get_level_values(0)
    return df.dropna(how="all")


def quality(symbol: str, df: pd.DataFrame) -> dict:
    if df.empty:
        return {"symbol": symbol, "rows": 0, "first": None, "last": None, "zero_volume_days": None}
    return {
        "symbol": symbol,
        "rows": len(df),
        "first": df.index.min().date(),
        "last": df.index.max().date(),
        "zero_volume_days": int((df["Volume"] == 0).sum()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--symbols", nargs="*", help="Boş bırakılırsa tüm liste")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    start = date.today() - timedelta(days=365 * args.years)
    symbols = [s.upper() for s in args.symbols] if args.symbols else load_symbols()
    symbols = symbols + [INDEX_TICKER.replace(".IS", "")] if not args.symbols else symbols

    report = []
    for i, sym in enumerate(symbols, 1):
        try:
            df = fetch_one(sym, start)
            if not df.empty:
                df.to_parquet(RAW_DIR / f"{sym}.parquet")
            report.append(quality(sym, df))
            print(f"[{i}/{len(symbols)}] {sym}: {len(df)} satır")
        except Exception as exc:  # bir hisse hata verirse diğerleri devam etsin
            print(f"[{i}/{len(symbols)}] {sym}: HATA {exc}")
            report.append({"symbol": sym, "rows": 0, "error": str(exc)})

    pd.DataFrame(report).to_csv(RAW_DIR / "_report.csv", index=False)
    empty = [r["symbol"] for r in report if not r.get("rows")]
    print(f"\nBitti. Boş gelen: {empty or 'yok'}")


if __name__ == "__main__":
    main()
