"""Piyasa verisi uçları: /assets, /history, /forecast, /analysis, /screener (gerçek veritabanıyla)."""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, text

from app.api import assets as assets_api
from tests.utils import auth_header, make_token

# Testin kendi kodları: başka testlerin verisine karışmaz, sonunda silinir
STOCK, STOCK2, FUND, INDEX, EMPTY = "TSTHY", "TSTAS", "TSTIP", "TSTXU", "TSTBOS"
CODES = (STOCK, STOCK2, FUND, INDEX, EMPTY)
LAST = date(2026, 9, 30)


@pytest.fixture(scope="module")
def seeded(database):
    eng = create_engine(database)
    with eng.begin() as c:
        c.execute(
            text("INSERT INTO assets(code, name, type, sector) VALUES (:c, :n, :t, :s)"),
            [
                {"c": STOCK, "n": "Test Hava Yolları", "t": "stock", "s": "Ulaştırma"},
                {"c": STOCK2, "n": "Test Savunma", "t": "stock", "s": "Savunma"},
                {"c": FUND, "n": "İş Test Banka Fonu", "t": "fund", "s": "Hisse Senedi Fonu"},
                {"c": INDEX, "n": "Test Endeks", "t": "index", "s": None},
                {"c": EMPTY, "n": "Fiyatsız", "t": "stock", "s": None},
            ],
        )
        rows = []
        for i in range(30):
            d = LAST - timedelta(days=29 - i)
            for code, base, step in ((STOCK, 100, 1.0), (STOCK2, 100, -0.5), (INDEX, 100, 2.0)):
                px = base + i * step
                rows.append({"c": code, "d": d, "o": px, "h": px + 2, "l": px - 1, "cl": px, "v": 1000})
            rows.append({"c": FUND, "d": d, "o": None, "h": None, "l": None, "cl": 4 + i * 0.01, "v": None})
        c.execute(
            text(
                "INSERT INTO prices(code, date, open, high, low, close, adj_close, volume) "
                "VALUES (:c, :d, :o, :h, :l, :cl, :cl, :v)"
            ),
            rows,
        )
        # Çok satırlı SQL: text() yerine doğrudan sürücüye (göç düzeltmesindeki gibi)
        c.exec_driver_sql(
            f"""
                INSERT INTO forecasts VALUES
                  ('{STOCK}', '2026-09-30', 'timesfm', 5, 120, 130, 140),
                  ('{STOCK}', '2026-09-30', 'chronos', 5, 118, 129, 141),
                  ('{STOCK}', '2026-09-30', 'timesfm', 120, 100, NULL, 180),
                  ('{STOCK}', '2026-09-29', 'timesfm', 5, 1, 1, 1);
                INSERT INTO scenarios VALUES
                  ('{STOCK}', '2026-09-30', 30, 110, 135, 160),
                  ('{STOCK}', '2026-09-30', 120, 90, 150, 210);
                INSERT INTO analysis(code, run_date, horizon, direction, confidence, risk, regime,
                                     weights, indicators, low, mid, high) VALUES
                  ('{STOCK}', '2026-09-30', 5, 'up', 72, 'medium', 'trend',
                   '{{"timesfm": 0.6, "chronos": 0.4}}', '{{"rsi": 61.2}}', 119, 129.6, 140.4),
                  ('{STOCK2}', '2026-09-30', 5, 'down', 66, 'high', 'high_vol', NULL, NULL, 80, 84, 88),
                  ('{FUND}', '2026-09-30', 5, 'up', 55, 'low', 'range', NULL, NULL, 4.2, 4.3, 4.4),
                  ('{STOCK}', '2026-09-29', 5, 'down', 10, 'low', 'range', NULL, NULL, 1, 2, 3);
                INSERT INTO ai_explanations VALUES
                  ('{STOCK}', '2026-09-30', 5, 'Modeller yükseliş yönünde uzlaşıyor.');
                """,
            execution_options={"no_parameters": True},
        )
    assets_api._list_cache.clear()
    yield
    with eng.begin() as c:
        for t in ("ai_explanations", "analysis", "scenarios", "forecasts", "prices", "assets"):
            c.execute(text(f"DELETE FROM {t} WHERE code = ANY(:codes)"), {"codes": list(CODES)})
    assets_api._list_cache.clear()
    eng.dispose()


@pytest.fixture
def h():
    return auth_header(make_token(email=f"{uuid.uuid4().hex[:8]}@example.com"))


def _ours(items):
    return [a for a in items if a["code"] in CODES]


# ---------------------------------------------------------------- /assets


def test_giris_gerekli(client, seeded):
    assert client.get("/assets").status_code == 401


def test_liste_son_fiyat_ve_degisim(client, seeded, h):
    items = {a["code"]: a for a in _ours(client.get("/assets", headers=h).json())}
    # Varsayılan: hisse + fon; endeks ve fiyatsız varlık yok
    assert set(items) == {STOCK, STOCK2, FUND}
    assert items[STOCK]["last_price"] == 129.0
    assert items[STOCK]["change_pct"] == pytest.approx((129 / 128 - 1) * 100, abs=1e-3)
    assert items[STOCK2]["change_pct"] < 0
    assert items[FUND]["type"] == "fund" and items[FUND]["sector"] == "Hisse Senedi Fonu"


def test_liste_tur_suzgeci_ve_endeks(client, seeded, h):
    assert {a["code"] for a in _ours(client.get("/assets?type=fund", headers=h).json())} == {FUND}
    assert {a["code"] for a in _ours(client.get("/assets?type=index", headers=h).json())} == {INDEX}


def test_istege_bagli_sayfalama(client, seeded, h):
    full = [a["code"] for a in client.get("/assets", headers=h).json()]
    p1 = [a["code"] for a in client.get("/assets?limit=2", headers=h).json()]
    p2 = [a["code"] for a in client.get("/assets?limit=2&offset=2", headers=h).json()]
    assert p1 == full[:2] and p2 == full[2:4]
    assert client.get(f"/assets?limit=5&offset={len(full)}", headers=h).json() == []
    assert client.get("/assets?limit=0", headers=h).status_code == 422


@pytest.mark.parametrize("q", ["İŞ TEST", "iş test", "IŞ TEST"])
def test_turkce_harf_duyarsiz_arama(client, seeded, h, q):
    assert [a["code"] for a in _ours(client.get(f"/assets?q={q}", headers=h).json())] == [FUND]


def test_kod_on_eki_ile_arama(client, seeded, h):
    assert {a["code"] for a in client.get("/assets?q=tsth", headers=h).json()} == {STOCK}


# ---------------------------------------------------------------- /history


def test_gecmis_son_n_gun_eskiden_yeniye(client, seeded, h):
    r = client.get(f"/assets/{STOCK}/history?days=5", headers=h).json()
    assert [p["date"] for p in r] == [str(LAST - timedelta(days=k)) for k in range(4, -1, -1)]
    assert r[-1]["close"] == 129.0 and r[-1]["volume"] == 1000


def test_fon_gecmisinde_ohlc_bos(client, seeded, h):
    p = client.get(f"/assets/{FUND}/history?days=3", headers=h).json()[-1]
    assert p["open"] is None and p["volume"] is None and p["close"] == pytest.approx(4.29)


def test_bilinmeyen_varlik_404_ve_kucuk_harf(client, seeded, h):
    assert client.get("/assets/YOKBOYLE/history", headers=h).status_code == 404
    assert client.get(f"/assets/{STOCK.lower()}/history?days=1", headers=h).status_code == 200


def test_days_sinirlari_422(client, seeded, h):
    assert client.get(f"/assets/{STOCK}/history?days=0", headers=h).status_code == 422
    assert client.get(f"/assets/{STOCK}/history?days=5000", headers=h).status_code == 422


# ---------------------------------------------------------------- /forecast


def test_tahmin_son_calisma_ensemble_ve_senaryolar(client, seeded, h):
    r = client.get(f"/assets/{STOCK}/forecast", headers=h).json()
    assert r["run_date"] == "2026-09-30"
    bands = {(b["model"], b["horizon"]): b for b in r["bands"]}
    assert bands[("ensemble", 5)] == {
        "model": "ensemble",
        "horizon": 5,
        "p10": 119.0,
        "p50": 129.6,
        "p90": 140.4,
    }
    assert bands[("timesfm", 5)]["p50"] == 130.0  # eski çalışmanın (1,1,1) değeri değil
    assert bands[("timesfm", 120)]["p50"] is None  # 120 günde nokta tahmin yok
    assert [s["horizon"] for s in r["scenarios"]] == [30, 120]


def test_tahmini_olmayan_varlik_404(client, seeded, h):
    assert client.get(f"/assets/{INDEX}/forecast", headers=h).status_code == 404


# ---------------------------------------------------------------- /analysis


def test_analiz_son_calisma_yorum_ve_range(client, seeded, h):
    r = client.get(f"/assets/{STOCK}/analysis?horizon=5", headers=h).json()
    assert r["run_date"] == "2026-09-30" and r["direction"] == "up" and r["confidence"] == 72
    assert r["range"] == {"low": 119.0, "mid": 129.6, "high": 140.4}
    assert r["weights"] == {"timesfm": 0.6, "chronos": 0.4}
    assert r["indicators"]["rsi"] == 61.2
    assert r["comment"] == "Modeller yükseliş yönünde uzlaşıyor."


def test_analiz_yorumsuz_ve_eksik_durumlar(client, seeded, h):
    assert client.get(f"/assets/{STOCK2}/analysis", headers=h).json()["comment"] is None
    assert client.get(f"/assets/{STOCK}/analysis?horizon=20", headers=h).status_code == 404
    assert client.get(f"/assets/{STOCK}/analysis?horizon=120", headers=h).status_code == 422


# ---------------------------------------------------------------- /screener


def test_tarayici_suzgec_ve_siralama(client, seeded, h):
    up = [a["code"] for a in _ours(client.get("/screener?direction=up", headers=h).json())]
    assert up == [STOCK, FUND]  # güvene göre azalan: 72, 55
    strict = [a["code"] for a in _ours(client.get("/screener?direction=up&min_conf=60", headers=h).json())]
    assert strict == [STOCK]
    funds = [a["code"] for a in _ours(client.get("/screener?type=fund", headers=h).json())]
    assert funds == [FUND]
    # horizon açıkça verilince de çalışmalı (sorgu parametresi metin olarak gelir)
    assert client.get("/screener?horizon=5", headers=h).status_code == 200
    assert client.get("/screener?horizon=20", headers=h).json() == []  # 20 günlük analiz yok
    assert client.get("/screener?horizon=7", headers=h).status_code == 422
