"""engine/indicators.py testleri: doğruluk, fonlar, bölünme günü ve VERİ SIZINTISI."""

import json
import math

import numpy as np
import pandas as pd

from engine import indicators as ind


def _stock(n: int = 300, seed: int = 7) -> pd.DataFrame:
    """Rastgele yürüyüşlü sentetik hisse (OHLCV)."""
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    spread = close * rng.uniform(0.005, 0.03, n)
    idx = pd.bdate_range("2025-01-01", periods=n)
    return pd.DataFrame(
        {
            "open": close * (1 + rng.normal(0, 0.005, n)),
            "high": close + spread,
            "low": close - spread,
            "close": close,
            "adj_close": close,
            "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
        },
        index=idx,
    )


def _fund(n: int = 120) -> pd.DataFrame:
    df = _stock(n)[["close"]].copy()
    df["adj_close"] = df["close"]
    for c in ("open", "high", "low", "volume"):
        df[c] = np.nan
    return df


def _wilder_rsi_loop(price: list[float], n: int) -> float:
    """Ders kitabı Wilder RSI'ı (döngüyle) — karşılaştırma için."""
    gains = [max(price[i] - price[i - 1], 0) for i in range(1, len(price))]
    losses = [max(price[i - 1] - price[i], 0) for i in range(1, len(price))]
    ag, al = gains[0], losses[0]
    a = 1 / n
    for g, lo in zip(gains[1:], losses[1:], strict=True):
        ag, al = ag + a * (g - ag), al + a * (lo - al)
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)


# --------------------------------------------------------------------------- doğruluk


def test_rsi_ders_kitabi_tanimiyla_ayni():
    df = _stock(200)
    ours = ind.rsi(df["close"], 14).iloc[-1]
    ref = _wilder_rsi_loop(df["close"].tolist(), 14)
    assert abs(ours - ref) < 1e-9


def test_rsi_sinirlar():
    up = pd.Series(np.arange(1, 60, dtype=float))
    flat = pd.Series(np.full(60, 10.0))
    assert ind.rsi(up, 14).iloc[-1] == 100.0
    assert ind.rsi(flat, 14).iloc[-1] == 50.0
    r = ind.rsi(_stock()["close"], 14).dropna()
    assert ((r >= 0) & (r <= 100)).all()


def test_rsi_yetersiz_gecmiste_nan():
    assert ind.rsi(pd.Series([1.0, 2, 3, 4, 5]), 14).isna().all()


def test_macd_sabit_fiyatta_sifir_ve_hist_tanimi():
    flat = pd.Series(np.full(80, 50.0))
    assert ind.macd(flat)["macd_hist"].dropna().abs().max() < 1e-12
    m = ind.macd(_stock()["close"]).dropna()
    assert np.allclose(m["macd_hist"], m["macd"] - m["macd_signal"])


def test_sma():
    s = pd.Series(np.arange(1, 11, dtype=float))
    assert ind.sma(s, 5).iloc[-1] == 8.0  # 6..10 ortalaması
    assert ind.sma(s, 5).iloc[3] != ind.sma(s, 5).iloc[3]  # NaN


def test_atr_sabit_aralikta_aralik_kadar():
    n = 100
    close = np.full(n, 100.0)
    df = pd.DataFrame(
        {"high": close + 1, "low": close - 1, "close": close, "adj_close": close, "volume": 1.0}
    )
    assert abs(ind.atr(df, 14).iloc[-1] - 2.0) < 1e-9


def test_bolunme_gunu_sahte_atr_uretmez():
    """2'ye 1 bölünme: ham fiyat yarıya iner, adj_close düzgündür → ATR sıçramamalı."""
    df = _stock(120)
    split = 80
    raw = df["close"].copy()
    raw.iloc[:split] *= 2  # bölünmeden önceki ham fiyatlar 2 katı
    df2 = df.copy()
    for c in ("open", "high", "low", "close"):
        df2[c] = df[c] * (raw / df["close"])
    # adj_close geriye dönük düzeltilmiş (eski df'nin kapanışı) — aynı kalır
    atr_ok = ind.atr(df, 14)
    atr_split = ind.atr(df2, 14)
    assert np.allclose(atr_ok.dropna(), atr_split.dropna())


def test_volatilite_sabit_buyumede_sifir():
    price = pd.Series(100 * 1.001 ** np.arange(60))
    assert ind.volatility(price, 20).iloc[-1] < 1e-9


def test_ma_kesisimi():
    # Önce düşen sonra hızla yükselen seri → MA20, MA50'yi bir kez yukarı keser
    price = pd.Series(np.r_[np.linspace(100, 60, 80), np.linspace(60, 140, 80)])
    df = pd.DataFrame({"close": price, "adj_close": price})
    t = ind.compute(df)
    assert (t["ma_cross"] == 1).sum() == 1
    assert (t["ma_cross"] == -1).sum() == 0


# --------------------------------------------------------------------------- VERİ SIZINTISI


def test_veri_sizintisi_yok_gelecek_veri_gecmisi_degistirmez():
    """t gününe kadar kesilmiş veriyle hesaplanan değer, tüm veriyle hesaplanan t değeriyle aynı olmalı.
    Gelecek veriyi kullanan (center=True, bfill, ileri kaydırma vb.) bir gösterge bu testi geçemez."""
    df = _stock(300)
    full = ind.compute(df)
    for t in (30, 60, 120, 200, 299):
        cut = ind.compute(df.iloc[: t + 1])
        a, b = full.iloc[t], cut.iloc[-1]
        for col in full.columns:
            x, y = a[col], b[col]
            assert (pd.isna(x) and pd.isna(y)) or abs(x - y) < 1e-9, f"{col} @ {t}: {x} != {y}"


def test_gelecekteki_soku_gecmis_gostergeler_gormez():
    df = _stock(200)
    before = ind.compute(df).iloc[149]
    shocked = df.copy()
    shocked.iloc[150:, :] *= 3  # 150. günden sonra büyük şok
    after = ind.compute(shocked).iloc[149]
    pd.testing.assert_series_equal(before, after)


# --------------------------------------------------------------------------- fonlar ve özet


def test_fonda_macd_ve_hacim_yok_atr_yerine_volatilite():
    t = ind.compute(_fund())
    assert "macd" not in t and "volume_change" not in t
    snap = ind.snapshot(t)
    assert "macd_hist" not in snap and "volume_change" not in snap
    assert snap["atr_pct"] is not None and snap["atr_pct"] > 0


def test_ozet_json_uyumlu_ve_nan_icermez():
    snap = ind.snapshot(ind.compute(_stock()))
    text = json.dumps(snap)  # NaN olsaydı geçersiz JSON üretirdi
    assert "NaN" not in text
    assert set(snap) >= {"rsi", "macd_hist", "ma20_above_ma50", "atr_pct", "vol20", "volume_change"}
    assert isinstance(snap["ma20_above_ma50"], bool)
    assert 0 <= snap["rsi"] <= 100


def test_kisa_gecmiste_ozet_none_doner():
    snap = ind.snapshot(ind.compute(_stock(10)))
    assert snap["rsi"] is None and snap["ma50"] is None and snap["ma20_above_ma50"] is None


def test_config_okunur():
    p = ind.load_params()
    assert p["rsi_period"] == 14 and p["macd"]["slow"] == 26
    assert not math.isnan(p["vol_window"])
