"""BIST günlük OHLCV toplayıcı (Görev 2) — yfinance.

- İlk çalıştırmada geriye dönük N yıl (varsayılan 5) çeker.
- Sonraki çalıştırmalarda her hisse için yalnızca son kayıtlı günden sonrasını çeker (artımlı).
- Sonuçlar yerel önbelleğe (data/cache/prices/<KOD>.csv) yazılır; aynı gün iki kez yazılmaz (upsert).
- DATABASE_URL tanımlıysa ve --db verilirse `prices` tablosuna ON CONFLICT ile upsert edilir.
- Bir hisse hata verirse iş durmaz; hatalar raporda listelenir.

Kullanım:
    python -m data.collectors.bist_prices                     # tüm liste, artımlı
    python -m data.collectors.bist_prices --codes THYAO GARAN --years 2
    python -m data.collectors.bist_prices --db                 # ayrıca veritabanına yaz
"""
from __future__ import annotations

import argparse
import os
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from data.collectors.bist_list import load_stock_list, to_yahoo

DATA_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = DATA_DIR / "cache" / "prices"
PRICE_COLUMNS = ["code", "date", "open", "high", "low", "close", "adj_close", "volume"]
INDEX_CODE = "XU100"  # BIST100 endeksi (rejim tespiti için, Kişi 2)

# yfinance sütun adı -> bizim sütun adımız
_YF_RENAME = {
    "Open": "open", "High": "high", "Low": "low", "Close": "close",
    "Adj Close": "adj_close", "Volume": "volume",
}


# ---------------------------------------------------------------- dönüştürme

def normalize_yf_frame(raw: pd.DataFrame, code: str) -> pd.DataFrame:
    """yfinance'ın döndürdüğü tabloyu `prices` biçimine çevirir."""
    if raw is None or raw.empty:
        return pd.DataFrame(columns=PRICE_COLUMNS)
    df = raw.copy()
    if isinstance(df.columns, pd.MultiIndex):  # yeni yfinance sürümleri
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=_YF_RENAME)
    if "adj_close" not in df.columns:  # auto_adjust=True gelirse
        df["adj_close"] = df["close"]
    df = df.dropna(subset=["close"])
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    df = df.reset_index(names="date")
    df["date"] = df["date"].dt.date
    df["code"] = code
    df["volume"] = df["volume"].fillna(0).astype("int64")
    return df[PRICE_COLUMNS].sort_values("date").reset_index(drop=True)


def merge_prices(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Upsert mantığı: aynı (code, date) varsa yeni satır kazanır."""
    if old is None or old.empty:
        return new.reset_index(drop=True)
    merged = pd.concat([old, new], ignore_index=True)
    merged = merged.drop_duplicates(subset=["code", "date"], keep="last")
    return merged.sort_values(["code", "date"]).reset_index(drop=True)


# ---------------------------------------------------------------- yerel önbellek

def cache_path(code: str, cache_dir: Path = CACHE_DIR) -> Path:
    return cache_dir / f"{code}.csv"


def read_cache(code: str, cache_dir: Path = CACHE_DIR) -> pd.DataFrame:
    path = cache_path(code, cache_dir)
    if not path.exists():
        return pd.DataFrame(columns=PRICE_COLUMNS)
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def write_cache(df: pd.DataFrame, code: str, cache_dir: Path = CACHE_DIR) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_path(code, cache_dir), index=False)


def next_start(existing: pd.DataFrame, default_start: date) -> date:
    """Artımlı güncelleme: son kayıtlı günden bir gün sonrası; kayıt yoksa varsayılan başlangıç.
    Son 3 günü yeniden çekeriz; yfinance son günü bazen sonradan düzeltir."""
    if existing.empty:
        return default_start
    return max(existing["date"]) - timedelta(days=3)


# ---------------------------------------------------------------- indirme

def download(code: str, start: date, retries: int = 3, backoff_s: float = 2.0) -> pd.DataFrame:
    """Tek hisse için OHLCV indirir; hata olursa üstel bekleme ile tekrar dener."""
    import yfinance as yf  # geç içe aktarma

    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            raw = yf.download(
                to_yahoo(code), start=start.isoformat(), auto_adjust=False,
                progress=False, threads=False,
            )
            return normalize_yf_frame(raw, code)
        except Exception as exc:
            last_exc = exc
            time.sleep(backoff_s * (2 ** attempt))
    raise RuntimeError(f"{code}: {retries} denemede indirilemedi: {last_exc}")


def update_code(code: str, default_start: date, cache_dir: Path = CACHE_DIR, fetch=download) -> dict:
    """Bir hissenin önbelleğini artımlı günceller, kısa bir rapor satırı döndürür."""
    old = read_cache(code, cache_dir)
    new = fetch(code, next_start(old, default_start))
    merged = merge_prices(old, new)
    if not merged.empty:
        write_cache(merged, code, cache_dir)
    return {
        "code": code,
        "new_rows": len(merged) - len(old),
        "total_rows": len(merged),
        "last_date": max(merged["date"]) if not merged.empty else None,
        "error": None if not merged.empty else "veri yok",
    }


# ---------------------------------------------------------------- veritabanı

def upsert_prices_db(df: pd.DataFrame, database_url: str, chunk: int = 5000) -> int:
    """`prices` tablosuna ON CONFLICT (code, date) DO UPDATE ile yazar."""
    from sqlalchemy import MetaData, Table, create_engine
    from sqlalchemy.dialects.postgresql import insert

    engine = create_engine(database_url)
    table = Table("prices", MetaData(), autoload_with=engine)
    records = df[PRICE_COLUMNS].to_dict("records")
    with engine.begin() as conn:
        for i in range(0, len(records), chunk):
            stmt = insert(table).values(records[i:i + chunk])
            stmt = stmt.on_conflict_do_update(
                index_elements=["code", "date"],
                set_={c: stmt.excluded[c] for c in PRICE_COLUMNS if c not in ("code", "date")},
            )
            conn.execute(stmt)
    return len(records)


# ---------------------------------------------------------------- giriş noktası

def run(codes: list[str], years: int, cache_dir: Path = CACHE_DIR, fetch=download) -> pd.DataFrame:
    default_start = date.today() - timedelta(days=365 * years)
    report = []
    for i, code in enumerate(codes, 1):
        try:
            row = update_code(code, default_start, cache_dir, fetch)
        except Exception as exc:  # bir hisse hata verirse diğerleri devam
            row = {"code": code, "new_rows": 0, "total_rows": 0, "last_date": None, "error": str(exc)}
        report.append(row)
        print(f"[{i}/{len(codes)}] {code}: +{row['new_rows']} satır"
              + (f"  HATA: {row['error']}" if row["error"] else ""))
    return pd.DataFrame(report)


def main() -> None:
    parser = argparse.ArgumentParser(description="BIST OHLCV toplayıcı")
    parser.add_argument("--codes", nargs="*", help="Boşsa bist_stocks.csv'deki tüm liste")
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--with-index", action="store_true", help="XU100 endeksini de çek")
    parser.add_argument("--db", action="store_true", help="DATABASE_URL'deki prices tablosuna da yaz")
    args = parser.parse_args()

    codes = [c.upper() for c in args.codes] if args.codes else load_stock_list()["code"].tolist()
    if args.with_index:
        codes.append(INDEX_CODE)

    report = run(codes, args.years)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    report.to_csv(CACHE_DIR / "_report.csv", index=False)

    if args.db:
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise SystemExit("--db için DATABASE_URL ortam değişkeni gerekli")
        ok = report.loc[report["error"].isna(), "code"]
        ok = [c for c in ok if c != INDEX_CODE]  # endeks assets'te yok (bkz. PR notu)
        frames = [read_cache(c) for c in ok]
        n = upsert_prices_db(pd.concat(frames, ignore_index=True), url) if frames else 0
        print(f"DB: {n} satır upsert edildi")

    errors = report.loc[report["error"].notna(), "code"].tolist()
    print(f"\nBitti. {len(report) - len(errors)}/{len(report)} başarılı. Hatalı: {errors or 'yok'}")


if __name__ == "__main__":
    main()
