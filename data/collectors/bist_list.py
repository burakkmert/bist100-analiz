"""BIST hisse listesi (Görev 1).

Kaynak: repoda tutulan `data/bist_stocks.csv` (code,name,sector).
- Liste elle veya KAP/Borsa İstanbul'dan alınan dosyayla güncellenir; tek doğru kaynak bu CSV'dir.
- `--enrich` ile boş kalan ad/sektör alanları yfinance'tan doldurulur.

Kullanım:
    python -m data.collectors.bist_list              # listeyi oku, özet yaz
    python -m data.collectors.bist_list --enrich     # boş ad/sektörleri yfinance ile doldur, CSV'ye kaydet

Çıktı biçimi `assets` tablosuyla aynıdır: code, name, type, sector, is_active, min_history_ok
"""
from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent
STOCKS_CSV = DATA_DIR / "bist_stocks.csv"

# BIST kodları 3-6 büyük harf/rakamdır (THYAO, A1CAP, ISCTR ...)
CODE_RE = re.compile(r"^[A-Z0-9]{3,6}$")
ASSET_COLUMNS = ["code", "name", "type", "sector", "is_active", "min_history_ok"]


def to_yahoo(code: str) -> str:
    """BIST kodunu yfinance sembolüne çevirir: THYAO -> THYAO.IS"""
    code = code.strip().upper()
    return code if code.endswith(".IS") else f"{code}.IS"


def load_stock_list(path: Path = STOCKS_CSV) -> pd.DataFrame:
    """CSV'yi okur, temizler ve `assets` biçiminde döndürür."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df["code"] = df["code"].str.strip().str.upper().str.replace(".IS", "", regex=False)

    bad = df.loc[~df["code"].str.match(CODE_RE), "code"].tolist()
    if bad:
        raise ValueError(f"Geçersiz hisse kodları: {bad}")

    df = df.drop_duplicates("code").sort_values("code").reset_index(drop=True)
    df["name"] = df["name"].str.strip().where(df["name"].str.strip() != "", df["code"])
    df["sector"] = df["sector"].str.strip().replace("", None)
    df["type"] = "stock"
    df["is_active"] = True
    df["min_history_ok"] = False  # fiyatlar geldikten sonra validate.py günceller
    return df[ASSET_COLUMNS]


def enrich_from_yfinance(df: pd.DataFrame, sleep_s: float = 0.3) -> pd.DataFrame:
    """Adı kodla aynı kalan (yani boş girilmiş) satırlar için yfinance'tan ad ve sektör çeker."""
    import yfinance as yf  # geç içe aktarma: testlerde gerekmez

    df = df.copy()
    for i, row in df.iterrows():
        if row["name"] != row["code"] and row["sector"]:
            continue
        try:
            info = yf.Ticker(to_yahoo(row["code"])).info or {}
            df.at[i, "name"] = info.get("longName") or info.get("shortName") or row["name"]
            df.at[i, "sector"] = row["sector"] or info.get("sector")
        except Exception as exc:  # tek hisse hata verirse devam
            print(f"{row['code']}: bilgi alınamadı ({exc})")
        time.sleep(sleep_s)
    return df


def save_stock_list(df: pd.DataFrame, path: Path = STOCKS_CSV) -> None:
    df[["code", "name", "sector"]].to_csv(path, index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="BIST hisse listesi")
    parser.add_argument("--enrich", action="store_true", help="Boş ad/sektörü yfinance ile doldur")
    args = parser.parse_args()

    df = load_stock_list()
    if args.enrich:
        df = enrich_from_yfinance(df)
        save_stock_list(df)
    missing_sector = int(df["sector"].isna().sum())
    print(f"{len(df)} hisse | sektörü boş: {missing_sector}")


if __name__ == "__main__":
    main()
