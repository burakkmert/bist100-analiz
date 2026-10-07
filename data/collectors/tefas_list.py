"""TEFAS fon listesi (Görev 1) — tefasmak.

Fon evreni: fon büyüklüğüne göre ilk N fon + izleme listesindeki ek fonlar (data/config.yaml).
Sonuç `data/tefas_funds.csv` dosyasına ve `assets` biçiminde döner.

Kullanım:
    python -m data.collectors.tefas_list           # listeyi TEFAS'tan çek, CSV'ye yaz
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = DATA_DIR / "config.yaml"
FUNDS_CSV = DATA_DIR / "tefas_funds.csv"
ASSET_COLUMNS = ["code", "name", "type", "sector", "is_active", "min_history_ok"]


def load_config(path: Path = CONFIG_FILE) -> dict:
    import yaml

    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _pick(row: dict, *keys, default=None):
    """tefasmak alan adları sürüme göre değişebilir; ilk bulunan anahtarı döndürür."""
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return row[k]
    return default


def rows_to_frame(fund_rows: list[dict], size_rows: list[dict]) -> pd.DataFrame:
    """tum_fonlar + fonlar_buyukluk çıktılarını tek tabloya çevirir: code, name, category, size."""
    funds = pd.DataFrame([
        {
            "code": str(_pick(r, "fonKodu", "kod", "code", default="")).strip().upper(),
            "name": _pick(r, "fonUnvan", "unvan", "title", "name", default=""),
            "category": _pick(r, "fonKategori", "fonTuru", "kategori"),
        }
        for r in fund_rows
    ])
    sizes = pd.DataFrame([
        {
            "code": str(_pick(r, "fonKodu", "kod", "code", default="")).strip().upper(),
            "size": float(_pick(r, "portBuyukluk", "portfoyBuyukluk", "buyukluk", default=0) or 0),
            "category_size": _pick(r, "fonKategori", "fonTuru", "kategori"),
        }
        for r in size_rows
    ])
    if sizes.empty:
        sizes = pd.DataFrame(columns=["code", "size", "category_size"])
    df = funds.merge(sizes, on="code", how="left")
    df["category"] = df["category"].fillna(df.pop("category_size"))
    df["size"] = df["size"].fillna(0.0)
    return df[df["code"] != ""].drop_duplicates("code")


def select_universe(df: pd.DataFrame, top_n: int, extra_codes: list[str]) -> pd.DataFrame:
    """Büyüklüğe göre ilk N + ek kodlar. Ek kod listede yoksa uyarı verilir."""
    top = df.sort_values("size", ascending=False).head(top_n)
    extra = {c.strip().upper() for c in extra_codes or []}
    missing = extra - set(df["code"])
    if missing:
        print(f"Uyarı: TEFAS listesinde bulunamayan ek fonlar: {sorted(missing)}")
    chosen = pd.concat([top, df[df["code"].isin(extra)]]).drop_duplicates("code")
    return chosen.sort_values("size", ascending=False).reset_index(drop=True)


def to_assets(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({
        "code": df["code"],
        "name": df["name"].where(df["name"].astype(str).str.len() > 0, df["code"]),
        "type": "fund",
        "sector": df["category"],     # fonlarda sektör yerine fon kategorisi
        "is_active": True,
        "min_history_ok": False,      # fiyatlar geldikten sonra validate.py günceller
    })
    return out[ASSET_COLUMNS]


def fetch_fund_universe(cfg: dict | None = None) -> pd.DataFrame:
    """TEFAS'tan listeyi çeker (2 istek), evreni seçer, assets biçiminde döndürür."""
    import tefasmak as tf

    cfg = (cfg or load_config())["fund_universe"]
    fund_type = cfg.get("fund_type", "YAT")
    fund_rows = tf.tum_fonlar(fund_type)
    size_rows = tf.fonlar_buyukluk(fon_tipi=fund_type)
    df = rows_to_frame(list(fund_rows), list(size_rows))
    chosen = select_universe(df, cfg.get("top_n_by_size", 300), cfg.get("extra_codes", []))
    return to_assets(chosen).assign(size=chosen["size"].values)


def load_fund_list(path: Path = FUNDS_CSV) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"code": str})


def main() -> None:
    df = fetch_fund_universe()
    df.to_csv(FUNDS_CSV, index=False)
    print(f"{len(df)} fon seçildi -> {FUNDS_CSV.name}")
    print(df.head(10)[["code", "name", "size"]].to_string(index=False))


if __name__ == "__main__":
    main()
