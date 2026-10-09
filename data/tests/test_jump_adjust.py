"""İmkânsız sıçrama düzeltmesi testleri — gerçek vakaların taklitleri.

Çalıştırma: pytest data/tests -q
"""
import numpy as np
import pandas as pd

from data.cleaning import adjust_jumps, clean_prices, implausible_jumps


def frame(prices, start="2024-07-01", freq="B"):
    dates = pd.date_range(start, periods=len(prices), freq=freq).date
    p = np.asarray(prices, dtype="float64")
    return pd.DataFrame({"code": "X", "date": dates, "close": p, "adj_close": p})


def returns(df):
    return df["adj_close"].pct_change().dropna().to_numpy()


def test_stock_bonus_issue_is_back_adjusted():
    # CCOLA tipi: %900 bedelsiz -> fiyat 1/10'a iner, sonra normal seyir
    raw = [500, 505, 510, 51.2, 51.5, 52.0]
    out = adjust_jumps(frame(raw), "stock")
    r = returns(out)
    assert np.abs(r).max() < 0.02                          # sahte çöküş yok
    assert np.isclose(out["adj_close"].iloc[-1], 52.0)     # son fiyat değişmez
    assert np.isclose(out["adj_close"].iloc[0], 500 * 51.2 / 510)   # geçmiş 1/10 ölçeklendi
    assert out["close"].tolist() == raw                    # ham kapanış korunur


def test_fund_spike_and_revert_cancels_out():
    # NTO tipi: bir gün hatalı kayıt (-%94), ardından eski seviyeye dönüş
    raw = [10.0, 10.1, 0.6, 10.2, 10.3]
    out = adjust_jumps(frame(raw), "fund")
    assert np.abs(returns(out)).max() < 0.02
    assert np.isclose(out["adj_close"].iloc[0], 10.0 * (0.6 / 10.1) * (10.2 / 0.6))  # ~10.1


def test_fund_unit_price_rescale():
    # GJH tipi: birim fiyat ×100 yeniden ayarlanır
    raw = [1.00, 1.01, 101.5, 102.0]
    out = adjust_jumps(frame(raw), "fund")
    assert np.abs(returns(out)).max() < 0.02


def test_real_moves_are_untouched():
    stock_limit_up = frame([100, 110, 121, 133.1])         # tavan serisi: her gün +%10, gerçek
    fund_big_day = frame([10, 10, 12.5, 12.6])             # fonda +%25: eşik %40, dokunulmaz
    for df, kind in [(stock_limit_up, "stock"), (fund_big_day, "fund")]:
        out = adjust_jumps(df, kind)
        assert np.allclose(out["adj_close"], df["adj_close"])


def test_stock_long_gap_widens_threshold():
    # İşlem durdurma: 3 hafta veri yok (15 iş günü), açılışta +%25 -> düzeltilmez
    df = pd.DataFrame({"code": "X", "date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-24"]).date,
                       "close": [100.0, 101.0, 126.0], "adj_close": [100.0, 101.0, 126.0]})
    assert not implausible_jumps(df, "stock").any()
    assert implausible_jumps(df.iloc[:2].assign(adj_close=[100.0, 120.0]), "stock").iloc[1]


def test_clean_prices_reports_with_type_thresholds():
    df = frame([100, 101, 85, 86])                         # hissede -%16 -> imkânsız, fonda olası
    _, stock_issues = clean_prices(df, asset_type="stock")
    _, fund_issues = clean_prices(df, asset_type="fund")
    assert len(stock_issues) == 1 and fund_issues.empty


def test_missing_session_widens_stock_limit():
    # Banka vakası: Cuma verisi eksik, Pazartesi iki seanslık +%17,6 -> gerçek hareket, dokunulmaz
    cal = pd.to_datetime(["2022-12-14", "2022-12-15", "2022-12-16", "2022-12-19"]).date.tolist()
    df = pd.DataFrame({"code": "VAKBN", "date": [cal[0], cal[1], cal[3]],
                       "close": [10.0, 10.1, 11.88], "adj_close": [10.0, 10.1, 11.88]})
    assert not implausible_jumps(df, "stock", calendar=cal).any()
    # Aynı hareket eksik gün olmadan (tek seans) -> imkânsız, düzeltilir
    df_full = pd.DataFrame({"code": "VAKBN", "date": cal[1:3],
                            "close": [10.1, 11.88], "adj_close": [10.1, 11.88]})
    assert implausible_jumps(df_full, "stock", calendar=cal).iloc[1]
