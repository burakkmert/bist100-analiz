"""Tahmin başarı metrikleri (Görev 6).

Hepsi saf fonksiyon: dizi alır, sayı döndürür. Backtest ve gece `model_errors` hesabı
aynı fonksiyonları kullanır.

Tanımlar (y = gerçekleşen, f = tahmin p50, y0 = tahmin anındaki son fiyat):
- MAE   = ort |y - f|
- MAPE  = ort |y - f| / |y|  (yüzde)
- MASE  = ort(|y - f| / y0) / ort(|y - y0| / y0)  — naive tahmin f = y0. < 1 ise model naive'i
          geçiyor. Hatalar tahmin anındaki fiyata bölünür (yüzde hata): 1 TL'lik fon ile 300 TL'lik
          hisse eşit ağırlık alır. (Klasik MASE ölçeği eğitim içi naive hatasıdır; burada aynı test
          noktalarında naive'in kendi hatası kullanılır. Tezde böyle tanımlanır.)
- Diebold–Mariano = iki modelin kaybı (|y - f| / y0) her tahmin gününde varlıklar üzerinden
          ortalanır, fark serisi Newey–West (HAC) varyansıyla test edilir. Varlıklar arası korelasyon
          ve üst üste binen ufuklar hesaba katılır. Binom p-değerleri bunları hesaba katmaz.
- Yön doğruluğu = ort [ sign(f - y0) == sign(y - y0) ]; yatay (f == y0) tahminler sayılmaz.
- Binom testi   = yön doğruluğu %50'den anlamlı farklı mı? (iki yönlü p-değeri)
- Kapsama       = ort [ p10 <= y <= p90 ]  — iyi kalibre %80 aralık için ~0.80 olmalı.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _arr(x) -> np.ndarray:
    return np.asarray(x, dtype="float64")


def mae(y, f) -> float:
    y, f = _arr(y), _arr(f)
    return float(np.mean(np.abs(y - f))) if len(y) else float("nan")


def mape(y, f) -> float:
    y, f = _arr(y), _arr(f)
    mask = y != 0
    return float(np.mean(np.abs((y[mask] - f[mask]) / y[mask])) * 100) if mask.any() else float("nan")


def mase(y, f, y0) -> float:
    """Naive'e (f = y0) göre göreli ortalama yüzde hata (ölçekten bağımsız)."""
    y, f, y0 = _arr(y), _arr(f), _arr(y0)
    naive = float(np.mean(np.abs(y - y0) / y0)) if len(y) else float("nan")
    return float(np.mean(np.abs(y - f) / y0)) / naive if naive > 0 else float("nan")


def newey_west_var(x: np.ndarray, lags: int) -> float:
    """Ortalamanın uzun dönem varyansı (Bartlett çekirdeği) — n'e bölünmemiş hâli."""
    x = np.asarray(x, dtype="float64") - np.mean(x)
    n = len(x)
    v = float(np.dot(x, x) / n)
    for k in range(1, min(lags, n - 1) + 1):
        w = 1 - k / (lags + 1)
        v += 2 * w * float(np.dot(x[k:], x[:-k]) / n)
    return max(v, 1e-18)


def diebold_mariano(loss_a, loss_b, lags: int) -> tuple[float, float]:
    """H0: iki modelin beklenen kaybı eşit. Negatif istatistik -> A daha iyi.
    Dönüş: (istatistik, iki yönlü p-değeri). Harvey-Leybourne-Newbold küçük örnek düzeltmesiyle."""
    from scipy.stats import t as student_t

    d = np.asarray(loss_a, dtype="float64") - np.asarray(loss_b, dtype="float64")
    d = d[np.isfinite(d)]
    n = len(d)
    if n < 5:
        return float("nan"), float("nan")
    stat = float(np.mean(d) / np.sqrt(newey_west_var(d, lags) / n))
    h = lags + 1
    stat *= np.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)   # HLN düzeltmesi
    p = float(2 * student_t.sf(abs(stat), df=n - 1))
    return stat, p


FLAT_TOL = 1e-6  # |f - y0| / y0 bundan küçükse "yatay" (float32 yuvarlaması yön sayılmasın)


def _sign(x, ref, tol=FLAT_TOL) -> np.ndarray:
    d = (x - ref) / np.abs(ref)
    return np.where(np.abs(d) <= tol, 0, np.sign(d))


def direction_hits(y, f, y0) -> tuple[int, int]:
    """(doğru yön sayısı, değerlendirilen tahmin sayısı). Yatay tahminler ve yatay
    gerçekleşmeler dışarıda bırakılır."""
    y, f, y0 = _arr(y), _arr(f), _arr(y0)
    pred, real = _sign(f, y0), _sign(y, y0)
    mask = (pred != 0) & (real != 0)
    return int((pred[mask] == real[mask]).sum()), int(mask.sum())


def direction_accuracy(y, f, y0) -> float:
    hits, n = direction_hits(y, f, y0)
    return hits / n if n else float("nan")


def binom_pvalue(hits: int, n: int, p: float = 0.5) -> float:
    """İki yönlü binom testi p-değeri: H0 = isabet oranı p."""
    if n == 0:
        return float("nan")
    from scipy.stats import binomtest

    return float(binomtest(hits, n, p, alternative="two-sided").pvalue)


def coverage(y, lo, hi) -> float:
    y, lo, hi = _arr(y), _arr(lo), _arr(hi)
    return float(np.mean((y >= lo) & (y <= hi))) if len(y) else float("nan")


def interval_width_pct(lo, hi, y0) -> float:
    """Ortalama aralık genişliği, son fiyata göre yüzde. Kapsama ile birlikte okunur:
    aynı kapsamada daha dar aralık daha iyidir."""
    lo, hi, y0 = _arr(lo), _arr(hi), _arr(y0)
    return float(np.mean((hi - lo) / y0) * 100) if len(y0) else float("nan")


def summarize(df: pd.DataFrame) -> dict:
    """Tek grup (ör. bir model × bir ufuk) için tüm metrikler.
    Gerekli sütunlar: y (gerçekleşen), y0 (tahmin anındaki fiyat), p10, p50, p90."""
    d = df.dropna(subset=["y", "y0", "p50"])
    hits, n_dir = direction_hits(d["y"], d["p50"], d["y0"])
    band = df.dropna(subset=["y", "p10", "p90"])
    return {
        "n": int(len(d)),
        "mae": mae(d["y"], d["p50"]),
        "mape": mape(d["y"], d["p50"]),
        "mase": mase(d["y"], d["p50"], d["y0"]),
        "dir_acc": hits / n_dir if n_dir else float("nan"),
        "dir_n": n_dir,
        "dir_pvalue": binom_pvalue(hits, n_dir),
        "coverage": coverage(band["y"], band["p10"], band["p90"]),
        "width_pct": interval_width_pct(band["p10"], band["p90"], band["y0"]) if "y0" in band else float("nan"),
    }


def summarize_by(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Gruplara göre metrik tablosu, ör. keys=["model", "horizon"]."""
    rows = [{**dict(zip(keys, k if isinstance(k, tuple) else (k,))), **summarize(g)}
            for k, g in df.groupby(keys, sort=True)]
    return pd.DataFrame(rows)


def dm_table(raw: pd.DataFrame, models: list[str], refs: list[str], step: int = 5,
             by: list[str] | None = None) -> pd.DataFrame:
    """Her (grup, ufuk, model, kıyas) için Diebold–Mariano testi.
    raw: walk-forward çıktısı (model, code, origin_date, horizon, y0, y, p50 [+ by sütunları])."""
    by = by or []
    d = raw.dropna(subset=["p50", "y", "y0"]).copy()
    d["loss"] = (d["y"] - d["p50"]).abs() / d["y0"]
    keys = by + ["horizon", "origin_date"]
    daily = d.groupby(keys + ["model"])["loss"].mean().unstack("model")   # tahmin günü × model
    rows = []
    for gkey, g in daily.groupby(level=by + ["horizon"]) if by else daily.groupby(level="horizon"):
        gkey = gkey if isinstance(gkey, tuple) else (gkey,)
        h = int(gkey[-1])
        lags = max(0, int(np.ceil(h / step)) - 1)       # üst üste binen ufuk sayısı
        for m in models:
            for r in refs:
                if m == r or m not in g or r not in g:
                    continue
                pair = g[[m, r]].dropna()
                stat, p = diebold_mariano(pair[m], pair[r], lags)
                rows.append({**dict(zip(by + ["horizon"], gkey)), "model": m, "vs": r,
                             "rel_loss": float(pair[m].mean() / pair[r].mean()) if len(pair) else np.nan,
                             "dm_stat": stat, "p_value": p, "n_days": len(pair)})
    return pd.DataFrame(rows)
