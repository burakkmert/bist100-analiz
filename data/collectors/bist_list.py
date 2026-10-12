"""BIST hisse listesi (Görev 1).

Kaynak: repoda tutulan `data/bist_stocks.csv` (code,name,sector).
- Tek doğru kaynak bu CSV'dir; gece işi listeyi buradan okur.
- `--update` ile İş Yatırım "Temel Değerler" sayfasındaki tüm BIST şirketleri çekilir,
  piyasa değerine göre ilk N hisse (data/config.yaml → stock_universe) CSV'ye yazılır.
  Ad ve sektör de aynı tablodan gelir.
- `--enrich` ile boş kalan ad/sektör alanları yfinance'tan doldurulur.

Kullanım:
    python -m data.collectors.bist_list                       # listeyi oku, özet yaz
    python -m data.collectors.bist_list --update --dry-run    # yeni evreni göster, kaydetme
    python -m data.collectors.bist_list --update              # evreni güncelle, CSV'ye kaydet
    python -m data.collectors.bist_list --update --html sayfa.html   # tarayıcıdan kaydedilmiş sayfa
    python -m data.collectors.bist_list --enrich              # boş ad/sektörleri yfinance ile doldur

Çıktı biçimi `assets` tablosuyla aynıdır: code, name, type, sector, is_active, min_history_ok
"""
from __future__ import annotations

import argparse
import re
import time
from html.parser import HTMLParser
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent
STOCKS_CSV = DATA_DIR / "bist_stocks.csv"
CONFIG_FILE = DATA_DIR / "config.yaml"
ISYATIRIM_URL = ("https://www.isyatirim.com.tr/tr-tr/analiz/hisse/Sayfalar/"
                 "Temel-Degerler-Ve-Oranlar.aspx")

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


# ---------------------------------------------------------------- evren güncelleme

class _TableParser(HTMLParser):
    """Sayfadaki tüm <table>'ları satır/hücre metni olarak toplar (iç içe tablolar dahil).
    pandas.read_html lxml/bs4 ister; ek bağımlılık olmasın diye standart kütüphane kullanılır."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._stack: list[list[list[str]]] = []   # açık tablolar
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._stack.append([])
        elif tag == "tr" and self._stack:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._stack:
            if self._row:
                self._stack[-1].append(self._row)
            self._row = None
        elif tag == "table" and self._stack:
            self.tables.append(self._stack.pop())

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def parse_tables(html: str) -> list[list[list[str]]]:
    p = _TableParser()
    p.feed(html)
    p.close()
    return p.tables


def tr_number(text: str) -> float:
    """Türkçe sayı biçimi: '3.125,3' -> 3125.3. Boş/'-' -> NaN."""
    s = str(text).strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return np.nan


def parse_isyatirim(html: str) -> pd.DataFrame:
    """İş Yatırım Temel Değerler sayfasından code, name, sector, mcap_tl tablosu çıkarır."""
    for table in parse_tables(html):
        for i, row in enumerate(table[:3]):                 # başlık ilk satırlarda
            low = [c.lower() for c in row]
            if "kod" not in low or not any(c.startswith("sektör") for c in low):
                continue
            mcap = [j for j, c in enumerate(low) if c.startswith("piyasa değeri") and "tl" in c]
            if not mcap:
                continue
            k, m = low.index("kod"), mcap[0]
            s = next(j for j, c in enumerate(low) if c.startswith("sektör"))
            n = next((j for j, c in enumerate(low) if "adı" in c or "unvan" in c), k + 1)
            rows = [r for r in table[i + 1:] if len(r) > max(k, n, s, m)]
            df = pd.DataFrame({
                "code": [r[k].strip().upper() for r in rows],
                "name": [r[n].strip() for r in rows],
                "sector": [r[s].strip() for r in rows],
                "mcap_tl": [tr_number(r[m]) for r in rows],
            })
            df = df[df["code"].str.match(CODE_RE)].drop_duplicates("code")
            if len(df) > 0:
                return df.reset_index(drop=True)
    raise ValueError("Sayfada 'Kod / Sektör / Piyasa Değeri (mn TL)' tablosu bulunamadı. "
                     "Sayfa yapısı değişmiş olabilir; --html ile kaydedilmiş sayfayı deneyin.")


def fetch_isyatirim_html(url: str = ISYATIRIM_URL, timeout: int = 60) -> str:
    """Sayfayı indirir. curl_cffi (tefasmak ile gelir) varsa tarayıcı gibi davranır."""
    try:
        from curl_cffi import requests as creq
        r = creq.get(url, impersonate="chrome", timeout=timeout)
        r.raise_for_status()
        return r.text
    except ImportError:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")


def load_universe_config(path: Path = CONFIG_FILE) -> dict:
    import yaml

    with open(path, encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}).get("stock_universe", {}) or {}


def select_universe(listing: pd.DataFrame, top_n: int, extra_codes: list[str] | None = None,
                    min_mcap_tl: float = 0.0) -> pd.DataFrame:
    """Piyasa değerine göre ilk `top_n` hisse + `extra_codes` (listede varsa).
    Piyasa değeri boş olanlar (işlem görmeyen/askıdaki) sona düşer."""
    df = listing.copy()
    df = df[df["mcap_tl"].fillna(0) >= min_mcap_tl] if min_mcap_tl > 0 else df
    df = df.sort_values("mcap_tl", ascending=False, na_position="last")
    chosen = df.head(top_n)
    extra = {c.strip().upper() for c in (extra_codes or [])}
    if extra:
        chosen = pd.concat([chosen, df[df["code"].isin(extra - set(chosen["code"]))]])
    return chosen.sort_values("code").reset_index(drop=True)[["code", "name", "sector", "mcap_tl"]]


def diff_report(old_codes: set[str], new_codes: set[str]) -> str:
    added, removed = sorted(new_codes - old_codes), sorted(old_codes - new_codes)
    show = lambda xs: ", ".join(xs[:15]) + (f" ... (+{len(xs) - 15})" if len(xs) > 15 else "")
    lines = [f"Eski: {len(old_codes)} | Yeni: {len(new_codes)} | "
             f"Eklenen: {len(added)} | Çıkan: {len(removed)}"]
    if added:
        lines.append(f"  Eklenen : {show(added)}")
    if removed:
        lines.append(f"  Çıkan   : {show(removed)}")
    return "\n".join(lines)


def update_universe(html: str | None = None, top_n: int | None = None, dry_run: bool = False,
                    path: Path = STOCKS_CSV) -> pd.DataFrame:
    cfg = load_universe_config()
    top_n = top_n or int(cfg.get("top_n_by_mcap", 500))
    listing = parse_isyatirim(html if html is not None else fetch_isyatirim_html())
    print(f"İş Yatırım: {len(listing)} şirket bulundu")

    old_codes = set(load_stock_list(path)["code"]) if path.exists() else set()
    # BIST-100 çekirdeği kaybolmasın: mevcut listede olup hâlâ işlem görenler korunur
    extra = list(cfg.get("extra_codes", []) or []) + sorted(old_codes)
    new = select_universe(listing, top_n, extra, float(cfg.get("min_mcap_mn_tl", 0) or 0))

    gone = sorted(old_codes - set(listing["code"]))
    if gone:
        print(f"Uyarı: mevcut listede olup sayfada olmayan {len(gone)} kod (işlemden kalkmış "
              f"veya kodu değişmiş olabilir), çıkarılıyor: {', '.join(gone)}")
    print(diff_report(old_codes, set(new["code"])))
    print(f"En küçük piyasa değeri (seçilen): {new['mcap_tl'].min():,.0f} mn TL")
    if not dry_run:
        save_stock_list(new, path)
        print(f"Kaydedildi: {path}")
    return new


def main() -> None:
    parser = argparse.ArgumentParser(description="BIST hisse listesi")
    parser.add_argument("--enrich", action="store_true", help="Boş ad/sektörü yfinance ile doldur")
    parser.add_argument("--update", action="store_true",
                        help="İş Yatırım'dan tüm şirketleri çek, piyasa değerine göre ilk N'i yaz")
    parser.add_argument("--html", help="--update için internetten çekmek yerine kaydedilmiş sayfa")
    parser.add_argument("--top", type=int, help="İlk kaç hisse (varsayılan config: top_n_by_mcap)")
    parser.add_argument("--dry-run", action="store_true", help="Değişikliği göster, kaydetme")
    args = parser.parse_args()

    if args.update:
        html = Path(args.html).read_text(encoding="utf-8", errors="replace") if args.html else None
        update_universe(html, args.top, args.dry_run)
        if args.dry_run:
            return

    df = load_stock_list()
    if args.enrich:
        df = enrich_from_yfinance(df)
        save_stock_list(df)
    missing_sector = int(df["sector"].isna().sum())
    print(f"{len(df)} hisse | sektörü boş: {missing_sector}")


if __name__ == "__main__":
    main()
