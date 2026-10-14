"""Güven skoru kalibrasyonu: Kişi 2'nin karar motoru geçmiş tahmin günlerinde yeniden çalıştırılır,
"güven 80–90" denen sinyaller gerçekte yüzde kaç tuttu ölçülür.

Neden: güven skoru 0–100 bir puandır; kullanıcı onu "olasılık gibi" okuyabilir. İyi kalibre bir skorda
güven arttıkça isabet oranı da artmalı ve kıyas oranının (rastgele isabet) üstünde olmalıdır.

Yöntem:
  * Her (varlık, tahmin günü) için engine.decision.analyze aynen çağrılır (motor koduna dokunulmaz).
    Fiyat geçmişi yalnızca tahmin gününe kadar kesilir; tahminler backtest ham sonucundan gelir
    (motorun ensemble'a aldığı modeller, eşit ağırlık: geçmiş model_errors arşivi yok).
  * Gerçek: backtest'in y (h gün sonraki fiyat) ve y0 (tahmin günü fiyatı) değerleri.
  * İsabet: up -> y > y0, down -> y < y0, flat -> |y/y0 - 1| <= atr_fraction × ATR% × √h
    (motorun flat eşiğiyle aynı; yani "hareket gürültü bandında kaldı").
  * Kıyas oranı: aynı (tür, ufuk, yön) için koşulsuz isabet oranı (güvene bakmadan).

Kullanım:
    python -m backtest.confidence_calibration --raw backtest/reports/raw_2026-10-12_u500.parquet
    python -m backtest.confidence_calibration --raw ... --every 2      # her 2. tahmin günü (hızlı)
Çıktı: ekrana tablo + backtest/reports/confidence_calibration_<raw adı>.csv
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

from data.collectors.bist_prices import read_cache
from data.cleaning import adjust_jumps, market_calendar, market_event_dates
from engine import decision as dec

REPORTS = Path(__file__).resolve().parent / "reports"
LOOKBACK_ROWS = 400                 # motorun gösterge/rejim hesabı için yeterli geçmiş (vol_lookback 252 + pay)
BUCKETS = [0, 50, 60, 70, 80, 90, 101]
BUCKET_LABELS = ["<50", "50-59", "60-69", "70-79", "80-89", "90-100"]


# ---------------------------------------------------------------- girdi

def load_ohlc_frames(codes: list[str], types: dict[str, str], reader=read_cache) -> dict[str, pd.DataFrame]:
    """Önbellekten OHLC çerçeveleri (tarih indeksli), motorun gördüğüyle aynı sıçrama düzeltmesiyle."""
    frames: dict[str, pd.DataFrame] = {}
    for code in codes:
        df = reader(code)
        if df is None or df.empty:
            continue
        frames[code] = df[df["close"] > 0].sort_values("date").drop_duplicates("date", keep="last")
    stock_frames = [f for c, f in frames.items() if types.get(c) == "stock"]
    cal = market_calendar(stock_frames)
    events = market_event_dates(stock_frames, cal)
    out = {}
    for code, df in frames.items():
        kind = "stock" if types.get(code) == "stock" else "fund"
        adj = adjust_jumps(df, kind, cal if kind == "stock" else None, events if kind == "stock" else None)
        adj = adj.set_index("date")
        for c in ("open", "high", "low", "close", "adj_close", "volume"):
            if c in adj:
                adj[c] = pd.to_numeric(adj[c], errors="coerce").astype(float)
        out[code] = adj
    return out


def forecast_map(raw: pd.DataFrame, models: list[str], horizons: list[int]) -> dict:
    """{(kod, tahmin günü): {ufuk: {model: (p10, p50, p90)}}} + {(kod, gün, ufuk): (y0, y)}."""
    r = raw[raw["model"].isin(models) & raw["horizon"].isin(horizons)]
    fc: dict = {}
    truth: dict = {}
    for row in r.itertuples(index=False):
        key = (row.code, row.origin_date)
        fc.setdefault(key, {}).setdefault(int(row.horizon), {})[row.model] = (row.p10, row.p50, row.p90)
        truth[(row.code, row.origin_date, int(row.horizon))] = (row.y0, row.y)
    return {"fc": fc, "truth": truth}


# ---------------------------------------------------------------- yeniden oynatma

def replay(raw: pd.DataFrame, frames: dict[str, pd.DataFrame], types: dict[str, str],
           cfg: dict | None = None, every: int = 1, log=print) -> pd.DataFrame:
    """Motoru her (varlık, tahmin günü) için çalıştırır. Dönüş: bir satır = (varlık, gün, ufuk)."""
    cfg = cfg or dec.load_config()
    models = cfg["ensemble"]["models"]
    horizons = [h for h in cfg["signals"]["horizons"] if h in set(raw["horizon"])]
    raw = raw.assign(origin_date=pd.to_datetime(raw["origin_date"]).dt.date)
    maps = forecast_map(raw, models, horizons)
    atr_fraction = cfg["direction"]["atr_fraction"]

    by_code: dict[str, list] = {}
    for code, origin in maps["fc"]:
        by_code.setdefault(code, []).append(origin)

    rows = []
    n_fail = 0
    for code, origins in by_code.items():
        px = frames.get(code)
        if px is None or len(px) < 60:
            continue
        dates = px.index.to_numpy()
        for origin in sorted(origins)[::every]:
            idx = int(np.searchsorted(dates, origin, side="right"))
            window = px.iloc[max(0, idx - LOOKBACK_ROWS):idx]
            if len(window) < 60 or window.index[-1] != origin:
                continue
            try:
                out = dec.analyze(code, origin, window, maps["fc"][(code, origin)], {}, cfg, types.get(code, "stock"))
            except Exception:  # noqa: BLE001 — tek satırın hatası kalibrasyonu durdurmasın
                n_fail += 1
                continue
            for r in out:
                h = int(r["horizon"])
                y0, y = maps["truth"].get((code, origin, h), (np.nan, np.nan))
                atr_pct = (r.get("indicators") or {}).get("atr_pct")
                tol = atr_fraction * (atr_pct or 0.0) / 100 * math.sqrt(h)   # göreli flat eşiği
                move = (y / y0 - 1) if y0 and np.isfinite(y0) and np.isfinite(y) else np.nan
                rows.append({"code": code, "type": types.get(code, "stock"), "origin": origin, "horizon": h,
                             "direction": r["direction"], "confidence": r["confidence"], "risk": r["risk"],
                             "move": move, "tol": tol})
    if n_fail:
        log(f"uyarı: {n_fail} (varlık, gün) için motor hata verdi, atlandı")
    return score(pd.DataFrame(rows))


def score(df: pd.DataFrame) -> pd.DataFrame:
    """İsabet (hit) ve kıyas için 'yukarı gitti mi' / 'bant içinde kaldı mı' sütunları."""
    if df.empty:
        return df.assign(hit=pd.Series(dtype=float), inside=pd.Series(dtype=float), up_move=pd.Series(dtype=float))
    df = df.dropna(subset=["move"]).copy()
    df["inside"] = (df["move"].abs() <= df["tol"]).astype(float)
    df["up_move"] = (df["move"] > 0).astype(float)
    df["hit"] = np.select([df["direction"] == "up", df["direction"] == "down", df["direction"] == "flat"],
                          [df["move"] > 0, df["move"] < 0, df["inside"] > 0], default=np.nan).astype(float)
    return df


# ---------------------------------------------------------------- kalibrasyon tablosu

def calibration_table(df: pd.DataFrame, min_n: int = 30) -> pd.DataFrame:
    """(tür, ufuk, yön, güven aralığı) başına: n, ortalama güven, isabet oranı, kıyas oranı.
    kıyas: flat için koşulsuz 'bant içinde kaldı' oranı; up/down için koşulsuz 'yukarı/aşağı gitti' oranı."""
    if df.empty:
        return pd.DataFrame(columns=["type", "horizon", "direction", "bucket", "n", "mean_conf", "hit_rate", "base_rate"])
    d = df.copy()
    d["bucket"] = pd.cut(d["confidence"], bins=BUCKETS, labels=BUCKET_LABELS, right=False)
    base = {}
    for (t, h), g in d.groupby(["type", "horizon"]):
        base[(t, h, "flat")] = g["inside"].mean()
        base[(t, h, "up")] = g["up_move"].mean()
        base[(t, h, "down")] = 1 - g["up_move"].mean()
    rows = []
    for (t, h, dirn, b), g in d.groupby(["type", "horizon", "direction", "bucket"], observed=True):
        if len(g) < min_n:
            continue
        rows.append({"type": t, "horizon": h, "direction": dirn, "bucket": str(b), "n": len(g),
                     "mean_conf": round(g["confidence"].mean(), 1), "hit_rate": round(g["hit"].mean(), 3),
                     "base_rate": round(base[(t, h, dirn)], 3)})
    return pd.DataFrame(rows)


def rank_correlation(df: pd.DataFrame, min_n: int = 100) -> pd.DataFrame:
    """Güven ile isabet arasındaki sıra korelasyonu (Spearman). İyi kalibre skorda pozitif olmalı."""
    rows = []
    for (t, h, dirn), g in df.groupby(["type", "horizon", "direction"]):
        if len(g) < min_n or g["confidence"].nunique() < 2 or g["hit"].nunique() < 2:
            continue
        rows.append({"type": t, "horizon": h, "direction": dirn, "n": len(g),
                     "spearman": round(g["confidence"].corr(g["hit"], method="spearman"), 3)})
    return pd.DataFrame(rows)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Güven skoru kalibrasyonu (motor yeniden oynatma)")
    p.add_argument("--raw", required=True, help="walk-forward ham sonuç parquet dosyası")
    p.add_argument("--every", type=int, default=1, help="her N. tahmin günü (hız için)")
    p.add_argument("--min-n", type=int, default=30, help="tabloda gösterilecek en az örnek")
    a = p.parse_args(argv)

    raw = pd.read_parquet(a.raw)
    if "type" in raw:
        types = dict(zip(raw["code"], raw["type"]))
    else:
        from ml.batch_forecast import load_universe_codes
        uni = load_universe_codes()
        types = dict(zip(uni["code"], uni["type"]))
    frames = load_ohlc_frames(sorted(raw["code"].unique()), types)
    print(f"{len(frames)} varlık yüklendi; motor yeniden oynatılıyor (birkaç dakika sürebilir)...")
    df = replay(raw, frames, types, every=a.every)

    pd.set_option("display.width", 200)
    pd.set_option("display.max_rows", 500)
    print(f"\n{len(df)} (varlık, gün, ufuk) değerlendirildi")
    print("\n== Yön dağılımı (tür, ufuk)")
    print(df.groupby(["type", "horizon"])["direction"].value_counts().unstack(fill_value=0).to_string())
    tab = calibration_table(df, a.min_n)
    print("\n== Güven aralığına göre isabet (hit_rate) ve kıyas oranı (base_rate)")
    print(tab.to_string(index=False))
    print("\n== Güven ↔ isabet sıra korelasyonu (Spearman; > 0 iyi)")
    print(rank_correlation(df).to_string(index=False))

    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / f"confidence_calibration_{Path(a.raw).stem}.csv"
    tab.to_csv(out, index=False)
    print(f"\nKaydedildi: {out}")


if __name__ == "__main__":
    main()
