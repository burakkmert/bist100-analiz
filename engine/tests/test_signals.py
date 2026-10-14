"""Sinyal motoru kuralları (saf)."""

from datetime import date, timedelta

from engine import decision as dec
from engine import signals as sig

CFG = dec.load_config()


def _a(h, direction="up", conf=80, risk="medium", high=110.0):
    return {"horizon": h, "direction": direction, "confidence": conf, "risk": risk, "high": high}


def _asset(code, price=100.0, atr_pct=2.0, rows=None):
    by_h = rows or {5: _a(5)}
    return sig.AssetView(code=code, price=price, atr_pct=atr_pct, by_horizon=by_h)


def _user(profile="balanced", budget=100_000, watch=("AAA",), positions=(), recent=()):
    return sig.UserView(
        user_id="u1",
        risk_profile=profile,
        budget=budget,
        watchlist=frozenset(watch),
        open_positions=list(positions),
        recent=frozenset(recent),
    )


# ---------------------------------------------------------------- alım


def test_izlenen_varlikta_alim_sinyali_adet_ve_zarar_durdur():
    (s,) = sig.buy_signals(_user(), {"AAA": _asset("AAA")}, CFG)
    assert (s.code, s.side, s.horizon, s.confidence) == ("AAA", "buy", 5, 80)
    assert s.suggested_qty == 100  # 100.000 × %10 / 100
    assert s.stop_level == 96.0  # 100 − 2 × (2% × 100)


def test_profil_esikleri():
    assets = {"AAA": _asset("AAA", rows={5: _a(5, conf=70)})}
    assert sig.buy_signals(_user("cautious"), assets, CFG) == []  # 70 < 75
    assert len(sig.buy_signals(_user("balanced"), assets, CFG)) == 1  # 70 ≥ 65
    assert len(sig.buy_signals(_user("aggressive"), assets, CFG)) == 1


def test_temkinli_profil_yuksek_riski_almaz():
    assets = {"AAA": _asset("AAA", rows={5: _a(5, conf=90, risk="high")})}
    assert sig.buy_signals(_user("cautious"), assets, CFG) == []
    assert len(sig.buy_signals(_user("aggressive"), assets, CFG)) == 1


def test_dusus_yonunde_alim_yok():
    assert sig.buy_signals(_user(), {"AAA": _asset("AAA", rows={5: _a(5, "down")})}, CFG) == []


def test_en_guvenli_ufuk_secilir_tek_sinyal():
    a = _asset("AAA", rows={1: _a(1, conf=70), 5: _a(5, conf=85), 20: _a(20, conf=75)})
    (s,) = sig.buy_signals(_user(), {"AAA": a}, CFG)
    assert s.horizon == 5 and s.confidence == 85


def test_acik_pozisyon_ve_bekleme_suresi_alimi_engeller():
    assets = {"AAA": _asset("AAA")}
    assert (
        sig.buy_signals(_user(positions=[{"id": 1, "code": "AAA", "qty": 5, "buy_price": 90}]), assets, CFG)
        == []
    )
    assert sig.buy_signals(_user(recent=[("AAA", "buy")]), assets, CFG) == []
    # sell bekleme süresi alımı engellemez
    assert len(sig.buy_signals(_user(recent=[("AAA", "sell")]), assets, CFG)) == 1


def test_taranan_evren_en_guclu_n_ve_ek_esik():
    n = CFG["signals"]["universe_top_n"]
    assets = {f"X{i}": _asset(f"X{i}", rows={5: _a(5, conf=76 + i)}) for i in range(n + 3)}
    assets["ZAYIF"] = _asset("ZAYIF", rows={5: _a(5, conf=70)})  # 70 < 65 + 10
    out = sig.buy_signals(_user(watch=()), assets, CFG)
    assert len(out) == n
    assert [s.confidence for s in out] == sorted((s.confidence for s in out), reverse=True)
    assert "ZAYIF" not in {s.code for s in out}


def test_butce_yoksa_adet_yok():
    (s,) = sig.buy_signals(_user(budget=None), {"AAA": _asset("AAA")}, CFG)
    assert s.suggested_qty is None
    assert sig.suggested_qty(50, 0.1, 100) is None  # 5 TL ile 1 adet alınamaz


# ---------------------------------------------------------------- satış


def _pos(**k):
    return {"id": 1, "code": "AAA", "qty": 7, "buy_price": 100.0, "stop_level": None, **k}


def test_model_dusus_satis_sinyali():
    assets = {"AAA": _asset("AAA", rows={5: _a(5, "down", conf=70)})}
    (s,) = sig.sell_signals(_user(positions=[_pos()]), assets, CFG)
    assert (s.side, s.reason, s.suggested_qty) == ("sell", "model", 7.0)


def test_zarar_durdur_satis_sinyali():
    # alış 100, ATR %2 × 90 = 1,8 → stop = 100 − 3,6 = 96,4; fiyat 90 < 96,4
    assets = {"AAA": _asset("AAA", price=90.0, rows={5: _a(5, "flat", conf=40)})}
    (s,) = sig.sell_signals(_user(positions=[_pos()]), assets, CFG)
    assert s.reason == "stop"


def test_sinyalin_kendi_zarar_durdur_seviyesi_kullanilir():
    assets = {"AAA": _asset("AAA", price=97.0, rows={5: _a(5, "flat", conf=40)})}
    assert sig.sell_signals(_user(positions=[_pos(stop_level=98.0)]), assets, CFG)[0].reason == "stop"
    assert sig.sell_signals(_user(positions=[_pos(stop_level=95.0)]), assets, CFG) == []


def test_hedef_bandi_asilinca_satis_sinyali():
    assets = {"AAA": _asset("AAA", price=115.0, rows={5: _a(5, "flat", conf=40, high=110.0)})}
    assert sig.sell_signals(_user(positions=[_pos()]), assets, CFG)[0].reason == "target"


def test_satis_bekleme_suresi():
    assets = {"AAA": _asset("AAA", rows={5: _a(5, "down", conf=90)})}
    assert sig.sell_signals(_user(positions=[_pos()], recent=[("AAA", "sell")]), assets, CFG) == []


# ---------------------------------------------------------------- sonuç


def test_sonuc_ufuk_dolmadan_yok_dolunca_hesaplanir():
    d0 = date(2026, 10, 1)
    closes = [(d0 + timedelta(days=i), 100 + i) for i in range(1, 4)]
    assert sig.evaluate_outcome("buy", 100, closes, 5) is None
    out = sig.evaluate_outcome("buy", 100, closes, 3)
    assert out["realized"] == 103 and out["hit"] is True and out["return_pct"] == 3.0
    assert sig.evaluate_outcome("sell", 100, closes, 3)["hit"] is False
