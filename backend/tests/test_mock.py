"""Mock mod: sözleşmedeki (shared/openapi.yaml) her Kişi 2 ucu ya gerçek ya da mock olarak cevap verir."""

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.api.mock import (
    SKIP_PREFIXES,
    load_spec,
    pick_example,
    register_mock_routes,
    tailor,
)

SPEC = load_spec()


def _mock_app(real_router: APIRouter | None = None) -> TestClient:
    app = FastAPI()
    if real_router:
        app.include_router(real_router)
    register_mock_routes(app, SPEC)
    return TestClient(app)


def _op(path: str, method: str) -> dict:
    return SPEC["paths"][path][method]


# ---------------------------------------------------------------- örnek seçimi (saf mantık)


def test_ornegi_olan_uc_kendi_ornegini_doner():
    status, body = pick_example(_op("/watchlist", "get"), SPEC)
    assert status == 200 and body == ["THYAO", "IPB"]


def test_ornegi_olmayan_screener_assets_ornegini_kullanir():
    _, assets = pick_example(_op("/assets", "get"), SPEC)
    _, screener = pick_example(_op("/screener", "get"), SPEC)
    assert screener == assets and len(screener) > 0


def test_patch_portfolio_pozisyon_orneginden_uretilir():
    status, body = pick_example(_op("/portfolio/{id}", "patch"), SPEC)
    assert status == 200
    assert {"id", "code", "qty", "buy_price"} <= set(body)


def test_204_govdesiz():
    assert pick_example(_op("/watchlist/{code}", "delete"), SPEC) == (204, None)


def test_tailor_code_ve_govde():
    out = tailor({"code": "THYAO", "qty": 10}, {"code": "asels"}, {}, {"qty": 3})
    assert out == {"code": "ASELS", "qty": 3}


def test_tailor_turkce_arama_ve_tur_suzgeci():
    rows = [
        {"code": "THYAO", "name": "Türk Hava Yolları", "type": "stock"},
        {"code": "IPB", "name": "İş Portföy Banka Fonu", "type": "fund"},
    ]
    assert [r["code"] for r in tailor(rows, {}, {"q": "iş"}, None)] == ["IPB"]
    assert [r["code"] for r in tailor(rows, {}, {"type": "stock"}, None)] == ["THYAO"]
    # Alan adı olmayan parametre (ör. min_conf) süzgeç değildir
    assert len(tailor(rows, {}, {"min_conf": "70"}, None)) == 2


# ---------------------------------------------------------------- HTTP düzeyi


def test_sozlesmedeki_her_kisi2_ucu_cevap_verir():
    """Mock modda sözleşmedeki hiçbir uç 404/405 dönmemeli (sözleşme kapsama testi)."""
    client = _mock_app()
    for path, ops in SPEC["paths"].items():
        if path.startswith(SKIP_PREFIXES) or path == "/health":
            continue
        url = path.replace("{code}", "THYAO").replace("{id}", "12")
        for method in ops:
            if method not in ("get", "post", "put", "patch", "delete"):
                continue
            r = client.request(method.upper(), url, json={} if method in ("post", "put", "patch") else None)
            assert r.status_code < 400, f"{method.upper()} {path} → {r.status_code}"
            assert r.headers.get("x-mock") == "1"


def test_analysis_istenen_kodu_doner():
    r = _mock_app().get("/assets/ASELS/analysis?horizon=5")
    assert r.status_code == 200
    assert r.json()["code"] == "ASELS"
    assert {"direction", "confidence", "risk", "range"} <= set(r.json())


def test_assets_tur_suzgeci():
    r = _mock_app().get("/assets?type=fund")
    assert r.status_code == 200
    assert r.json() and all(a["type"] == "fund" for a in r.json())


def test_post_portfolio_201_ve_gonderileni_yansitir():
    body = {"code": "ASELS", "qty": 5, "buy_price": 60.25, "buy_date": "2026-10-13"}
    r = _mock_app().post("/portfolio", json=body)
    assert r.status_code == 201
    assert r.json()["code"] == "ASELS" and r.json()["qty"] == 5 and "id" in r.json()


def test_gercek_uc_mock_tarafindan_ezilmez():
    real = APIRouter()

    @real.get("/watchlist")
    def watchlist():
        return ["GERCEK"]

    client = _mock_app(real)
    r = client.get("/watchlist")
    assert r.json() == ["GERCEK"]
    assert "x-mock" not in r.headers
    # Aynı yolun mock'lanmamış diğer metodu yine mock
    assert client.post("/watchlist", json={"code": "THYAO"}).status_code == 204


def test_ana_uygulamada_profil_ve_ai_gercek_kalir(client):
    """MOCK kapalıyken (testlerin varsayılanı) mock uçları eklenmez."""
    paths = client.get("/openapi.json").json()["paths"]
    assert "/me/profile" in paths
    assert "/assets" not in paths  # gerçek /assets henüz yazılmadı; mock kapalı
