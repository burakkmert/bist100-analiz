"""Karar motoru: ensemble ağırlıkları, rejim, yön, güven skoru, risk ve analysis satırı."""

import json
import math

import numpy as np
import pandas as pd
import pytest

from engine import decision as dec
from engine import ensemble as ens
from engine import regime as reg

CFG = dec.load_config()


def _series(n=300, drift=0.0, vol=0.01, seed=1, ohlc=True, volume=2_000_000):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(drift, vol, n)))
    df = pd.DataFrame({"close": close, "adj_close": close}, index=pd.bdate_range("2025-01-01", periods=n))
    if ohlc:
        spread = close * vol
        df["open"], df["high"], df["low"] = close, close + spread, close - spread
        df["volume"] = float(volume)
    else:
        df[["open", "high", "low", "volume"]] = np.nan
    return df


# ---------------------------------------------------------------- ensemble


def test_agirlik_1_bolu_mae_ve_toplam_1():
    w = ens.weights(["a", "b"], {"a": 1.0, "b": 3.0}, min_weight=0)
    assert w["a"] == pytest.approx(0.75) and w["b"] == pytest.approx(0.25)


def test_hata_yoksa_esit_agirlik():
    w = ens.weights(["timesfm", "chronos", "naive_drift"], {})
    assert all(v == pytest.approx(1 / 3) for v in w.values())


def test_hatasi_bilinmeyen_model_ortalama_agirlik_alir():
    w = ens.weights(["a", "b", "c"], {"a": 1.0, "b": 1.0}, min_weight=0)
    assert w["c"] == pytest.approx(w["a"])


def test_alt_sinir_uygulanir():
    w = ens.weights(["iyi", "kotu"], {"iyi": 1.0, "kotu": 1000.0}, min_weight=0.1)
    assert w["kotu"] == pytest.approx(0.1) and w["iyi"] == pytest.approx(0.9)
    assert sum(w.values()) == pytest.approx(1)


def test_birlestirme_agirlikli_kantil_ortalamasi_ve_sira():
    fc = {"a": (90, 100, 110), "b": (110, 120, 130)}
    e = ens.combine(fc, {"a": 1.0, "b": 1.0})
    assert (e.p10, e.p50, e.p90) == (100, 110, 120)
    assert e.p10 <= e.p50 <= e.p90


def test_p50_yoksa_orta_nokta():
    e = ens.combine({"a": (90, None, 110)}, {})
    assert e.p50 == 100


def test_gecerli_tahmin_yoksa_hata():
    with pytest.raises(ValueError):
        ens.combine({"a": (None, 1, None)}, {})


def test_uyum_payi():
    fc = {"a": (95, 105, 115), "b": (85, 95, 105)}
    assert ens.agreement(fc, {"a": 0.7, "b": 0.3}, 100, "up") == pytest.approx(0.7)
    assert ens.agreement(fc, {"a": 0.7, "b": 0.3}, 100, "flat") == pytest.approx(1.0)


# ---------------------------------------------------------------- rejim


def test_guclu_trend_trend_rejimi():
    n = 300
    close = 100 * 1.004 ** np.arange(n) * (1 + 0.002 * np.sin(np.arange(n)))
    df = pd.DataFrame(
        {"close": close, "adj_close": close, "high": close * 1.005, "low": close * 0.995, "volume": 1e6},
        index=pd.bdate_range("2025-01-01", periods=n),
    )
    assert reg.classify(df).name == "trend"


def test_yatay_seri_range_rejimi():
    n = 300
    close = 100 + 2 * np.sin(np.arange(n) / 3)
    df = pd.DataFrame(
        {"close": close, "adj_close": close, "high": close + 0.5, "low": close - 0.5, "volume": 1e6},
        index=pd.bdate_range("2025-01-01", periods=n),
    )
    assert reg.classify(df).name == "range"


def test_son_gunlerde_oynaklik_patlamasi_high_vol():
    df = _series(300, vol=0.005, seed=3)
    rng = np.random.default_rng(9)
    shock = 100 * np.exp(np.cumsum(rng.normal(0, 0.06, 25)))
    df.iloc[-25:, df.columns.get_loc("close")] = df["close"].iloc[-26] * shock / 100
    df["adj_close"] = df["close"]
    df["high"], df["low"] = df["close"] * 1.03, df["close"] * 0.97
    r = reg.classify(df)
    assert r.name == "high_vol" and r.details["vol_percentile"] > 0.8


def test_fonda_verimlilik_orani_kullanilir():
    r = reg.classify(_series(300, drift=0.004, vol=0.002, ohlc=False))
    assert "efficiency_ratio" in r.details and "adx" not in r.details
    assert r.name == "trend"


# ---------------------------------------------------------------- karar


def _fc(last, move, width=3.0):
    """Üç model, son fiyattan `move` kadar kayık bant."""
    m = last + move
    return {
        "timesfm": (m - width, m, m + width),
        "chronos": (m - width, m + 0.2, m + width),
        "naive_drift": (m - width, m - 0.2, m + width),
    }


def test_belirgin_yukselis_up_ve_yuksek_guven():
    df = _series(300, drift=0.001, seed=4)
    last = float(df["close"].iloc[-1])
    rows = dec.analyze("THYAO", "2026-10-13", df, {5: _fc(last, last * 0.05)}, {5: {}}, CFG)
    (r,) = rows
    assert r["direction"] == "up"
    assert r["confidence"] >= 70
    assert r["low"] <= r["mid"] <= r["high"]


def test_kucuk_degisim_flat():
    df = _series(300, seed=5)
    last = float(df["close"].iloc[-1])
    (r,) = dec.analyze("X", "2026-10-13", df, {5: _fc(last, 0.0)}, {5: {}}, CFG)
    assert r["direction"] == "flat"


def test_modeller_ayrisinca_guven_duser():
    df = _series(300, seed=6)
    last = float(df["close"].iloc[-1])
    agree = _fc(last, last * 0.05)
    split = {
        "timesfm": (last * 1.10 - 3, last * 1.10, last * 1.10 + 3),
        "chronos": (last * 0.97 - 3, last * 0.97, last * 0.97 + 3),
        "naive_drift": (last * 0.98 - 3, last * 0.98, last * 0.98 + 3),
    }
    hi = dec.analyze("X", "d", df, {5: agree}, {5: {}}, CFG)[0]["confidence"]
    lo = dec.analyze("X", "d", df, {5: split}, {5: {"timesfm": 1, "chronos": 1, "naive_drift": 1}}, CFG)[0]
    assert lo["confidence"] < hi


def test_dusuk_likidite_ve_kisa_gecmis_cezasi():
    df = _series(120, seed=7, volume=100)  # günlük ~10 bin TL, 120 gün
    last = float(df["close"].iloc[-1])
    r = dec.analyze("X", "d", df, {5: _fc(last, last * 0.05)}, {5: {}}, CFG)[0]
    pen = r["indicators"]["confidence_parts"]["penalties"]
    assert pen["low_liquidity"] == CFG["confidence"]["penalty_low_liquidity"]
    assert pen["short_history"] == CFG["confidence"]["penalty_short_history"]


def test_fonda_likidite_cezasi_yok():
    df = _series(300, seed=8, ohlc=False)
    last = float(df["close"].iloc[-1])
    r = dec.analyze("IPB", "d", df, {5: _fc(last, last * 0.03, width=0.5)}, {5: {}}, CFG, asset_type="fund")[
        0
    ]
    assert r["indicators"]["confidence_parts"]["penalties"]["low_liquidity"] == 0
    assert "macd_hist" not in r["indicators"]


def test_gosterge_celiskisi_cezasi():
    assert dec.indicator_conflicts("up", {"rsi": 75, "ma20_above_ma50": False, "macd_hist": -1}) == [
        "rsi_asiri_alim",
        "ortalamalar_dusus_yonlu",
    ]
    assert dec.indicator_conflicts("down", {"rsi": 50, "ma20_above_ma50": True, "macd_hist": 0.5}) == [
        "ortalamalar_yukselis_yonlu"
    ]
    assert dec.indicator_conflicts("flat", {"rsi": 90}) == []


def test_risk_seviyesi_ture_gore():
    r = {
        "stock": {"low_below": 35, "medium_below": 55},
        "fund": {"low_below": 10, "medium_below": 25},
        "high_vol_bump": 1,
    }
    assert dec.risk_level(30, "trend", r) == "low"
    assert dec.risk_level(40, "range", r) == "medium"
    assert dec.risk_level(60, "trend", r) == "high"
    assert dec.risk_level(30, "trend", r, "fund") == "high"  # fon için %30 çok oynak
    assert dec.risk_level(5, "trend", r, "fund") == "low"
    assert dec.risk_level(30, "trend", r, "index") == "low"  # tanımsız tür → hisse eşikleri
    assert dec.risk_level(None, "trend", r) == "medium"


def test_yuksek_oynaklik_riski_bir_kademe_artirir():
    r = {"stock": {"low_below": 35, "medium_below": 55}, "high_vol_bump": 1}
    assert dec.risk_level(30, "high_vol", r) == "medium"
    assert dec.risk_level(40, "high_vol", r) == "high"
    assert dec.risk_level(80, "high_vol", r) == "high"


def test_config_risk_esikleri_gecerli():
    for t in ("stock", "fund", "index"):
        th = CFG["risk"][t]
        assert 0 < th["low_below"] < th["medium_below"]


def test_flat_guveni_sinirli_ve_guc_puani_yok():
    """Hepsi 'yön yok' diyorsa bu yüksek güvenli bir sinyal değildir (Kişi 1'in gözlemi: hisselerde
    %99 flat ama ortalama güven 87-89 idi)."""
    df = _series(300, seed=5)
    last = float(df["close"].iloc[-1])
    (r,) = dec.analyze("X", "d", df, {5: _fc(last, 0.0)}, {5: {}}, CFG)
    parts = r["indicators"]["confidence_parts"]
    assert r["direction"] == "flat"
    assert parts["strength"] == 0
    assert r["confidence"] <= CFG["confidence"]["flat_max"]
    up = dec.analyze("X", "d", df, {5: _fc(last, last * 0.05)}, {5: {}}, CFG)[0]
    assert up["confidence"] > r["confidence"]


def test_flat_uyumu_esige_gore():
    fc = {"yakin": (90, 100.5, 110), "uzak": (90, 108, 120)}
    w = {"yakin": 0.6, "uzak": 0.4}
    assert ens.agreement(fc, w, 100, "flat", threshold=2) == pytest.approx(0.6)
    assert ens.agreement(fc, w, 100, "flat") == pytest.approx(1.0)  # eşiksiz eski davranış (bant)


def test_satir_analysis_tablosuna_uygun_ve_json():
    df = _series(300, seed=10)
    last = float(df["close"].iloc[-1])
    fcs = {h: _fc(last, last * 0.02 * math.sqrt(h)) for h in (1, 5, 20)}
    rows = dec.analyze("THYAO", "2026-10-13", df, fcs, {}, CFG)
    assert [r["horizon"] for r in rows] == [1, 5, 20]
    for r in rows:
        assert set(r) == {
            "code",
            "run_date",
            "horizon",
            "direction",
            "confidence",
            "risk",
            "regime",
            "weights",
            "indicators",
            "low",
            "mid",
            "high",
        }
        assert r["direction"] in ("up", "down", "flat")
        assert 0 <= r["confidence"] <= 100 and isinstance(r["confidence"], int)
        assert r["risk"] in ("low", "medium", "high") and r["regime"] in ("trend", "range", "high_vol")
        assert sum(r["weights"].values()) == pytest.approx(1, abs=1e-3)
        json.dumps(r["indicators"])  # NaN/numpy içermemeli


def test_120_gun_analiz_uretmez():
    df = _series(300, seed=11)
    last = float(df["close"].iloc[-1])
    rows = dec.analyze("X", "d", df, {120: _fc(last, 10)}, {}, CFG)
    assert rows == []
