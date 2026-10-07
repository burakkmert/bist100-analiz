"""TEFAS toplayıcı testleri. İnternet gerekmez: tefasmak yerine sahte veri kullanılır.

Çalıştırma: pytest data/tests -q
"""
from datetime import date, timedelta
from pathlib import Path
import tempfile

import pandas as pd

from data.collectors.tefas_list import rows_to_frame, select_universe, to_assets
from data.collectors.tefas_prices import normalize_tefas_rows, parse_tefas_date, read_cache, run


def fake_series(start: date, days: int, base: float = 1.0) -> list[dict]:
    return [{"tarih": (start + timedelta(days=i)).isoformat(), "fiyat": base + i * 0.01} for i in range(days)]


# ---------------------------------------------------------------- tefas_list

def test_rows_to_frame_and_universe():
    funds = [{"fonKodu": f"F{i:02d}", "fonUnvan": f"Fon {i}", "fonKategori": "Hisse"} for i in range(10)]
    sizes = [{"fonKodu": f"F{i:02d}", "portBuyukluk": i * 1000} for i in range(10)]
    df = rows_to_frame(funds, sizes)
    chosen = select_universe(df, top_n=3, extra_codes=["f01", "YOK"])
    assert chosen["code"].tolist() == ["F09", "F08", "F07", "F01"]  # ilk 3 + izlenen
    assets = to_assets(chosen)
    # gerçek TEFAS alan adları: fonlar_gunluk_detay_hepsi ve tum_fonlar
    real = [{"fonKodu": "IPB", "fonUnvan": "İstanbul Portföy", "portfoyBuyukluk": 5e9},
            {"fonKod": "TTE", "unvan": "İş Portföy", "portfoyBuyukluk": 9e9}]
    df2 = rows_to_frame(real, real)
    assert df2.sort_values("size")["code"].tolist() == ["IPB", "TTE"]
    assert df2.set_index("code").loc["TTE", "name"] == "İş Portföy"
    assert set(assets["type"]) == {"fund"} and assets["sector"].iloc[0] == "Hisse"


# ---------------------------------------------------------------- tefas_prices

def test_parse_tefas_date_formats():
    d = date(2026, 10, 7)
    assert parse_tefas_date("2026-10-07") == d
    assert parse_tefas_date("07.10.2026") == d
    ms = int(pd.Timestamp("2026-10-07").timestamp() * 1000)
    assert parse_tefas_date(ms) == d and parse_tefas_date(str(ms)) == d


def test_normalize_skips_bad_rows_and_fills_close_only():
    rows = [
        {"fonKodu": "IPB", "tarih": "2026-10-06", "fiyat": "1,25"},  # virgüllü ondalık
        {"fonKodu": "IPB", "tarih": "2026-10-07", "fiyat": 0},       # sıfır fiyat atlanır
        {"fonKodu": "TTE", "tarih": "2026-10-07", "fiyat": None},    # boş fiyat atlanır
    ]
    df = normalize_tefas_rows(rows)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["code"] == "IPB" and row["close"] == 1.25 == row["adj_close"]
    assert pd.isna(row["open"]) and pd.isna(row["volume"])


def test_run_initial_then_incremental_and_errors():
    today = date(2026, 10, 7)
    calls = {"full": [], "bulk": 0}

    def full_fetch(code):
        calls["full"].append(code)
        if code == "BOZUK":
            raise RuntimeError("TEFAS hatası")
        return normalize_tefas_rows(fake_series(today - timedelta(days=30), 25), code)

    def bulk_fetch(start, end):
        calls["bulk"] += 1
        rows = [{**r, "fonKodu": c} for c in ("IPB", "TTE")
                for r in fake_series(start, (end - start).days + 1, base=2.0)]
        return normalize_tefas_rows(rows)

    with tempfile.TemporaryDirectory() as d:
        cache = Path(d)
        r1 = run(["IPB", "TTE", "BOZUK"], cache_dir=cache, today=today,
                 full_fetch=full_fetch, bulk_fetch=bulk_fetch)
        r2 = run(["IPB", "TTE"], cache_dir=cache, today=today,
                 full_fetch=full_fetch, bulk_fetch=bulk_fetch)
        ipb = read_cache("IPB", cache)

    r1 = r1.set_index("code")
    assert r1.loc["BOZUK", "error"] == "TEFAS hatası" and r1.loc["TTE", "new_rows"] == 25
    assert calls["full"] == ["IPB", "TTE", "BOZUK"]   # ikinci turda tam çekim yok
    assert calls["bulk"] == 1                          # iki fon için tek toplu istek
    assert max(ipb["date"]) == today and ipb["date"].is_unique
    assert r2.set_index("code").loc["IPB", "new_rows"] == 6  # eksik 6 gün eklendi
