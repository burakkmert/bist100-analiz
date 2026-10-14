"""Güven kalibrasyonu: Kişi 1'in eşlemesi → gösterilecek geçmiş isabet, flat tavanı, sinyal kapısı."""

import json

import numpy as np
import pandas as pd

from engine import calibration as cal
from engine import decision as dec
from engine import signals as sig

MAPPING = {
    "version": 1,
    "keys": {
        "fund|5|up": {
            "informative": True,
            "base_rate": 0.6,
            "fitted": {"<50": 0.55, "60-69": 0.7, "80-89": 0.9},
            "suggested_cap": None,
        },
        "stock|5|up": {"informative": False, "base_rate": 0.5, "fitted": {"<50": 0.5, "90-100": 0.51}},
        "stock|5|flat": {
            "informative": False,
            "base_rate": 0.57,
            "fitted": {"90-100": 0.57},
            "suggested_cap": 40,
        },
    },
}


def test_kova():
    assert cal.bucket_of(0) == "<50" and cal.bucket_of(49.9) == "<50"
    assert cal.bucket_of(50) == "50-59" and cal.bucket_of(89) == "80-89" and cal.bucket_of(100) == "90-100"


def test_ayirt_edici_anahtarda_gecmis_isabet_gosterilir():
    d = cal.describe(MAPPING, "fund", 5, "up", 85)
    assert d["shown"] is True and d["hit_rate"] == 0.9
    assert d["message"] == "Geçmişte benzer model sinyallerinde isabet oranı %90 (kıyas: %60)."
    # Örneği olmayan kova → en yakın kova
    assert cal.describe(MAPPING, "fund", 5, "up", 72)["hit_rate"] == 0.7


def test_ayirt_edici_olmayan_anahtarda_oran_gosterilmez():
    d = cal.describe(MAPPING, "stock", 5, "up", 95)
    assert d["shown"] is False and "hit_rate" not in d and "ayırt" in d["reason"]
    assert cal.describe(MAPPING, "fund", 20, "down", 70) == {"shown": False, "reason": "yetersiz geçmiş veri"}
    assert cal.describe(None, "fund", 5, "up", 70) is None


def test_mesajda_tavsiye_dili_yok():
    for args in (("fund", 5, "up", 85), ("stock", 5, "up", 95)):
        msg = cal.describe(MAPPING, *args)["message"].lower()
        assert " al" not in msg and " sat" not in msg and "tavsiye" not in msg


def test_flat_tavani_ve_bilgilendiricilik():
    assert cal.flat_cap(MAPPING, "stock", 5, 50) == 40
    assert cal.flat_cap(MAPPING, "fund", 5, 50) == 50  # eşlemede yok → varsayılan
    assert cal.informative(MAPPING, "fund", 5, "up") is True
    assert cal.informative(MAPPING, "stock", 5, "up") is False
    assert cal.informative(MAPPING, "fund", 1, "up") is False  # anahtar yok
    assert cal.informative(None, "stock", 5, "up") is True  # eşleme yoksa kısıtlama yok


def test_dosyadan_yukleme(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps(MAPPING), encoding="utf-8")
    assert cal.load(p)["keys"]["fund|5|up"]["informative"] is True
    assert cal.load(tmp_path / "yok.json") is None


def _series(n=300, seed=5):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    df = pd.DataFrame({"close": close, "adj_close": close}, index=pd.bdate_range("2025-01-01", periods=n))
    df["open"], df["high"], df["low"], df["volume"] = close, close * 1.01, close * 0.99, 2e6
    return df


def test_motor_kalibrasyonla_flat_tavani_ve_aciklama_ekler():
    df = _series()
    last = float(df["close"].iloc[-1])
    fc = {m: (last - 3, last, last + 3) for m in ("timesfm", "chronos", "naive_drift")}
    cfg = dec.load_config()
    (raw,) = dec.analyze("X", "d", df, {5: fc}, {}, cfg)
    (r,) = dec.analyze("X", "d", df, {5: fc}, {}, cfg, "stock", MAPPING)
    assert r["direction"] == "flat" and r["confidence"] <= 40
    assert "calibration" not in raw["indicators"]  # backtest yeniden oynatması ham puanı görür
    assert r["indicators"]["calibration"]["shown"] is False


def test_sinyal_yalniz_ayirt_edici_ufukta():
    rows = {
        5: {"horizon": 5, "direction": "up", "confidence": 90, "risk": "low", "high": 120},
        20: {"horizon": 20, "direction": "up", "confidence": 70, "risk": "low", "high": 130},
    }
    free = sig.AssetView("X", 100, 2.0, rows)
    gated = sig.AssetView("X", 100, 2.0, rows, "fund", frozenset({(20, "up")}))
    assert sig.best_horizon(free, "up", 65, {"low"})["horizon"] == 5
    assert sig.best_horizon(gated, "up", 65, {"low"})["horizon"] == 20
    none = sig.AssetView("X", 100, 2.0, rows, "stock", frozenset())
    assert sig.best_horizon(none, "up", 65, {"low"}) is None
