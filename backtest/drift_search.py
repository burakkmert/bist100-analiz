"""Fonlarda trend (naive_drift) iyileştirme deneyi: kategori bazında trend penceresi ve yumuşatma.

Soru: fon kategorisine göre trend penceresi (kaç günlük ortalama getiri) ve trend yumuşatma katsayısı
doğru seçilirse, sabit ayardan (250 gün, yumuşatma yok) gerçekten daha iyi tahmin elde edilir mi?

Yöntem (kendimizi kandırmamak için):
  * Varyantlar: pencere ∈ {20, 60, 120, 250, 500} × yumuşatma ∈ {0,5, 0,75, 1,0}
    (merkez = son fiyat × exp(yumuşatma × ortalama günlük log-getiri × h); üretimdeki ayar = 250 / 1,0).
  * Tahmin günleri zamana göre ikiye bölünür (arada 30 gün boşluk). Her (kategori, ufuk) için en iyi
    varyant İLK yarıda seçilir; İKİNCİ yarıda "seçilen" ile "üretimdeki ayar" karşılaştırılır
    (yüzde hata oranı + Diebold–Mariano). Ayarı da ölçümü de aynı veride yapmayız.
  * Çok küçük kategoriler (< 15 fon) tek bir "diger" grubunda birleştirilir.
  * Karar: seçilen ayar ancak test yarısında anlamlı (p < 0,05) ve kayıp oranı < 1 ise önerilir.

Kullanım:
    python -m backtest.drift_search
    python -m backtest.drift_search --step 10 --test-days 252      # hızlı deneme
Çıktı: ekrana tablolar + backtest/reports/drift_search_<tarih>.csv + backtest/summary/drift_search.csv
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from backtest.by_category import load_fund_categories
from backtest.metrics import dm_table
from backtest.walk_forward import run_walk_forward
from ml.models.baselines import NaiveDriftForecaster

REPORTS = Path(__file__).resolve().parent / "reports"
SUMMARY = Path(__file__).resolve().parent / "summary"
WINDOWS = [20, 60, 120, 250, 500]
SHRINKS = [0.5, 0.75, 1.0]
BASELINE = "w250_s100"          # üretimdeki naive_drift (pencere 250, yumuşatma yok)
HORIZONS = [1, 5, 20, 30]       # 120g: embargo çok uzun olurdu; bu ufukta nokta tahmin zaten yok
MIN_FUNDS = 15
EMBARGO_DAYS = 30


class DampedDrift(NaiveDriftForecaster):
    """Trendli naive; trend `shrink` ile çarpılarak yumuşatılır (aşırı uzatmayı azaltmak için)."""

    def __init__(self, window: int, shrink: float, **kw):
        super().__init__(drift_window=window, **kw)
        self.shrink = shrink
        self.name = variant_name(window, shrink)

    def center(self, prices, h):
        logp = np.log(prices[-(self.drift_window + 1):].astype("float64"))
        mu = (logp[-1] - logp[0]) / (len(logp) - 1) if len(logp) > 1 else 0.0
        mu = float(np.clip(mu, -self.max_daily, self.max_daily)) * self.shrink
        return float(prices[-1] * np.exp(mu * h))


def variant_name(window: int, shrink: float) -> str:
    return f"w{window}_s{int(round(shrink * 100))}"


def make_variants(windows=WINDOWS, shrinks=SHRINKS) -> list[DampedDrift]:
    return [DampedDrift(w, s) for w in windows for s in shrinks]


def assign_categories(codes: list[str], cats: pd.Series, min_funds: int = MIN_FUNDS) -> dict[str, str]:
    """Fon -> kategori; küçük kategoriler 'diger' altında birleşir."""
    cat = {c: cats.get(c, "diger") for c in codes}
    counts = pd.Series(cat).value_counts()
    small = set(counts[counts < min_funds].index)
    return {c: ("diger" if k in small else k) for c, k in cat.items()}


def time_split(raw: pd.DataFrame, embargo_days: int = EMBARGO_DAYS) -> tuple[pd.DataFrame, pd.DataFrame]:
    o = pd.to_datetime(raw["origin_date"])
    cut = o.sort_values().iloc[len(o) // 2]
    return raw[o <= cut], raw[o > cut + pd.Timedelta(days=embargo_days)]


def loss_table(raw: pd.DataFrame) -> pd.DataFrame:
    """(kategori, ufuk, model) -> ortalama yüzde hata |y - p50| / y0."""
    d = raw.dropna(subset=["p50", "y", "y0"]).copy()
    d["loss"] = (d["y"] - d["p50"]).abs() / d["y0"]
    return d.groupby(["category", "horizon", "model"])["loss"].mean().rename("loss").reset_index()


def select_best(train: pd.DataFrame) -> pd.DataFrame:
    """Her (kategori, ufuk) için eğitim yarısında en düşük hatalı varyant."""
    lt = loss_table(train)
    best = lt.loc[lt.groupby(["category", "horizon"])["loss"].idxmin()]
    return best.rename(columns={"model": "selected", "loss": "train_loss"})[["category", "horizon", "selected", "train_loss"]]


def test_selection(test: pd.DataFrame, chosen: pd.DataFrame, step: int = 5) -> pd.DataFrame:
    """Test yarısında seçilen varyant vs üretimdeki ayar. rel_loss < 1: seçilen daha iyi."""
    m = test.merge(chosen[["category", "horizon", "selected"]], on=["category", "horizon"])
    sel = m[m["model"] == m["selected"]].assign(model="secilen")
    base = m[m["model"] == BASELINE].assign(model="taban")
    both = pd.concat([sel, base], ignore_index=True)
    dm = dm_table(both, ["secilen"], ["taban"], step=step, by=["category"])
    if dm.empty:
        return dm
    dm = dm.merge(chosen[["category", "horizon", "selected", "train_loss"]], on=["category", "horizon"])
    dm["oneri"] = (dm["rel_loss"] < 1) & (dm["p_value"] < 0.05) & (dm["selected"] != BASELINE)
    return dm[["category", "horizon", "selected", "train_loss", "rel_loss", "rel_loss_median", "p_value",
               "n_days", "oneri"]]


def overall(test: pd.DataFrame, chosen: pd.DataFrame, step: int = 5) -> pd.DataFrame:
    """Tüm fonlar tek grup: seçimin toplam kazancı (ufuk bazında)."""
    m = test.merge(chosen[["category", "horizon", "selected"]], on=["category", "horizon"])
    both = pd.concat([m[m["model"] == m["selected"]].assign(model="secilen"),
                      m[m["model"] == BASELINE].assign(model="taban")], ignore_index=True)
    return dm_table(both, ["secilen"], ["taban"], step=step)[["horizon", "rel_loss", "rel_loss_median", "p_value", "n_days"]]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Fon trend penceresi/yumuşatma araması (kategori bazında)")
    p.add_argument("--test-days", type=int, default=504)
    p.add_argument("--step", type=int, default=5)
    a = p.parse_args(argv)

    from ml.batch_forecast import load_price_frames, load_universe_codes
    from ml.models.base import load_config

    cfg = load_config()
    uni = load_universe_codes()
    funds = uni[uni["type"] == "fund"]
    types = dict(zip(funds["code"], funds["type"]))
    frames, _ = load_price_frames(funds["code"].tolist(), cfg.get("min_history", 120), types=types)
    print(f"{len(frames)} fon, {len(WINDOWS) * len(SHRINKS)} varyant")
    raw, _ = run_walk_forward(frames, make_variants(), HORIZONS, a.test_days, a.step,
                              cfg.get("min_history", 120), cfg["context_length"])
    cats = load_fund_categories()
    raw["category"] = raw["code"].map(assign_categories(list(frames), cats))

    pd.set_option("display.width", 220)
    pd.set_option("display.max_rows", 200)
    train, test = time_split(raw)
    print(f"\neğitim: {len(train)} satır | test: {len(test)} satır")
    chosen = select_best(train)
    print("\n== Eğitim yarısında seçilen varyant (kategori × ufuk)")
    print(chosen.pivot(index="category", columns="horizon", values="selected").to_string())

    res = test_selection(test, chosen, a.step)
    print("\n== Test yarısı: seçilen / üretimdeki ayar (rel_loss < 1 ve p < 0,05 → anlamlı iyileşme)")
    print(res.round(4).to_string(index=False))
    print("\n== Tüm fonlar, ufuk bazında")
    print(overall(test, chosen, a.step).round(4).to_string(index=False))

    REPORTS.mkdir(exist_ok=True)
    SUMMARY.mkdir(exist_ok=True)
    out = REPORTS / f"drift_search_{date.today().isoformat()}.csv"
    res.to_csv(out, index=False)
    res.round(4).to_csv(SUMMARY / "drift_search.csv", index=False)
    print(f"\nKaydedildi: {out}\n           {SUMMARY / 'drift_search.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
