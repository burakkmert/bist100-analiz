"""Güven eşlemesi testleri: sentetik veri; internet/DB gerekmez."""
import numpy as np
import pandas as pd

from backtest.confidence_mapping import (capped_confidence, display_confidence, evaluate, fit_mapping,
                                         pav, summarize, time_split)


def synth(n: int = 6000, seed: int = 0) -> pd.DataFrame:
    """İki anahtar: fon|5|up -> güven isabeti gerçekten artırır; hisse|5|flat -> güven rastgele (isabet hep ~0,57)."""
    rng = np.random.default_rng(seed)
    origin = pd.Timestamp("2025-01-01") + pd.to_timedelta(rng.integers(0, 400, 2 * n), unit="D")
    conf = rng.integers(30, 100, 2 * n)
    fund = pd.DataFrame({"type": "fund", "horizon": 5, "direction": "up", "confidence": conf[:n], "origin": origin[:n],
                         "hit": (rng.random(n) < (0.6 + 0.4 * (conf[:n] - 30) / 70)).astype(float)})
    stock = pd.DataFrame({"type": "stock", "horizon": 5, "direction": "flat", "confidence": conf[n:], "origin": origin[n:],
                          "hit": (rng.random(n) < 0.57).astype(float)})
    d = pd.concat([fund, stock], ignore_index=True)
    d["inside"] = np.where(d["direction"] == "flat", d["hit"], 0.57)
    d["up_move"] = np.where(d["direction"] == "up", d["hit"], 0.5)
    return d


def test_pav_makes_values_nondecreasing_and_keeps_weighted_mean():
    out = pav([0.9, 0.5, 0.7], [10, 10, 20])
    assert all(a <= b + 1e-12 for a, b in zip(out, out[1:]))
    assert abs(sum(v * w for v, w in zip(out, [10, 10, 20])) - (9 + 5 + 14)) < 1e-9
    assert pav([0.1, 0.2, 0.3], [1, 1, 1]) == [0.1, 0.2, 0.3]


def test_informative_only_where_confidence_discriminates():
    m = fit_mapping(synth())
    assert m["keys"]["fund|5|up"]["informative"] is True
    assert m["keys"]["stock|5|flat"]["informative"] is False
    assert m["keys"]["stock|5|flat"]["suggested_cap"] is not None


def test_display_and_cap():
    m = fit_mapping(synth())
    hi = display_confidence(m, "fund", 5, "up", 95)
    lo = display_confidence(m, "fund", 5, "up", 35)
    assert hi["shown"] and lo["shown"] and hi["hit_rate"] > lo["hit_rate"]
    assert "Geçmişte benzer sinyallerin" in hi["message"]
    assert not display_confidence(m, "stock", 5, "flat", 96)["shown"]
    assert not display_confidence(m, "stock", 20, "up", 80)["shown"]          # bilinmeyen anahtar
    cap = m["keys"]["stock|5|flat"]["suggested_cap"]
    assert capped_confidence(m, "stock", 5, "flat", 96) == min(96, cap) <= 70
    assert capped_confidence(m, "fund", 5, "up", 96) == 96                    # yalnızca flat sınırlanır


def test_time_split_has_embargo_and_no_overlap():
    d = synth()
    tr, te = time_split(d, embargo_days=30)
    assert pd.to_datetime(tr["origin"]).max() < pd.to_datetime(te["origin"]).min() - pd.Timedelta(days=29)
    assert len(tr) > 0 and len(te) > 0


def test_mapped_probabilities_are_better_calibrated_than_raw_score_out_of_sample():
    tr, te = time_split(synth(12000, seed=3))
    ev = evaluate(fit_mapping(tr), te)
    shown = ev[ev["informative"]]
    assert len(shown) == 1 and shown["ece_mapped"].iloc[0] < shown["ece_raw"].iloc[0]
    s = summarize(ev).set_index("type")
    assert s.loc["fund", "ece_esleme_gosterilen"] < s.loc["fund", "ece_ham_gosterilen"]
    assert s.loc["stock", "guven_gosterilen_pay"] == 0.0                      # hissede güven gösterilmez
