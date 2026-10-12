"""Fon kategorisi kırılımı testleri."""
import numpy as np
import pandas as pd

from backtest.by_category import category_from_name, category_tables, normalize_category


def test_category_from_name_turkish_upper_case():
    assert category_from_name("İŞ PORTFÖY PARA PİYASASI (TL) FONU") == "para_piyasasi"
    assert category_from_name("HEDEF PORTFÖY BİRİNCİ HİSSE SENEDİ SERBEST FON") == "hisse"
    assert category_from_name("AK PORTFÖY ALTIN FONU") == "altin_maden"
    assert category_from_name("YAPI KREDİ KİRA SERTİFİKALARI KATILIM FONU") == "borclanma"
    assert category_from_name("X PORTFÖY BİRİNCİ SERBEST FON") == "serbest"
    assert category_from_name("Y PORTFÖY DEĞİŞKEN FON") == "degisken_karma"
    assert category_from_name("TUHAF BİR AD") == "diger"


def test_tefas_category_preferred_over_name():
    assert normalize_category("Borçlanma Araçları Fonu", "X SERBEST FON") == "borclanma"
    assert normalize_category(None, "X SERBEST FON") == "serbest"
    assert normalize_category("", "Z PARA PİYASASI FONU") == "para_piyasasi"


def test_category_tables_groups_and_compares():
    rng = np.random.default_rng(0)
    days = pd.bdate_range("2025-01-01", periods=30)
    rows = []
    for code in ["PPF", "HSF"]:
        for d in days:
            y0, y = 100.0, 100.0 + rng.normal(0, 1)
            for model, err in [("timesfm", 1.0), ("naive_drift", 0.5), ("naive", 2.0)]:
                p50 = y + err
                rows.append({"type": "fund", "code": code, "origin_date": d, "horizon": 30,
                             "model": model, "y0": y0, "y": y, "p10": p50 - 3, "p50": p50, "p90": p50 + 3})
    raw = pd.DataFrame(rows)
    cats = pd.Series({"PPF": "para_piyasasi", "HSF": "hisse"})
    summ, dm = category_tables(raw, cats, [30], ["timesfm"], "naive_drift")
    assert set(summ["category"]) == {"para_piyasasi", "hisse"}
    assert set(dm["category"]) == {"para_piyasasi", "hisse"}
    assert (dm["rel_loss"] > 1.9).all()          # timesfm hatası naive_drift'in 2 katı
