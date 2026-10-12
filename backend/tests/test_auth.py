"""Supabase JWT doğrulama, profil uçları ve kullanıcılar arası veri yalıtımı."""

import uuid

import pytest

from app.core.config import get_settings
from tests.utils import auth_header, make_token


def _email() -> str:
    # users.email UNIQUE olduğu için her test kendi e-postasını kullanır
    return f"{uuid.uuid4().hex[:10]}@example.com"


def test_token_yoksa_401(client):
    r = client.get("/me/profile")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_gecersiz_imza_401(client):
    token = make_token(email=_email(), secret="baska-bir-gizli-anahtar-en-az-32-karakter!!")
    assert client.get("/me/profile", headers=auth_header(token)).status_code == 401


def test_suresi_dolmus_token_401(client):
    token = make_token(email=_email(), exp_in=-10)
    assert client.get("/me/profile", headers=auth_header(token)).status_code == 401


def test_yanlis_audience_401(client):
    # Supabase'in anon anahtarı gibi "authenticated" olmayan tokenlar kabul edilmez
    token = make_token(email=_email(), audience="anon")
    assert client.get("/me/profile", headers=auth_header(token)).status_code == 401


def test_ilk_giriste_kullanici_ve_varsayilan_profil_olusur(client):
    email = _email()
    r = client.get("/me/profile", headers=auth_header(make_token(email=email)))
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == email
    assert body["risk_profile"] == "balanced"
    assert body["budget"] is None
    assert body["quiet_hours"] is None
    assert body["daily_push_limit"] == 5


def test_profil_guncelleme_ve_kalicilik(client):
    h = auth_header(make_token(email=_email()))
    r = client.put(
        "/me/profile",
        headers=h,
        json={
            "risk_profile": "cautious",
            "budget": 50000,
            "quiet_hours": {"start": "22:30", "end": "08:00"},
        },
    )
    assert r.status_code == 200, r.text
    again = client.get("/me/profile", headers=h).json()
    assert again["risk_profile"] == "cautious"
    assert again["budget"] == 50000  # JSON'da sayı (mobil `number` bekliyor)
    assert again["quiet_hours"] == {"start": "22:30", "end": "08:00"}


def test_mobilin_gonderdigi_govde_kabul_edilir(client):
    """mobile/api/profile.ts yalnızca {risk_profile, budget} gönderir."""
    h = auth_header(make_token(email=_email()))
    r = client.put("/me/profile", headers=h, json={"risk_profile": "aggressive", "budget": None})
    assert r.status_code == 200
    assert r.json()["risk_profile"] == "aggressive"


@pytest.mark.parametrize(
    "body",
    [
        {"risk_profile": "yolo"},
        {"budget": -1},
        {"quiet_hours": {"start": "25:00", "end": "08:00"}},
    ],
)
def test_gecersiz_girdi_422(client, body):
    h = auth_header(make_token(email=_email()))
    assert client.put("/me/profile", headers=h, json=body).status_code == 422


def test_kullanici_baskasinin_profilini_degistiremez(client):
    """A kullanıcısının değişikliği B kullanıcısını etkilemez."""
    a, b = uuid.uuid4(), uuid.uuid4()
    eb = _email()
    ha = auth_header(make_token(a, _email()))
    hb = auth_header(make_token(b, eb))

    client.put("/me/profile", headers=ha, json={"risk_profile": "aggressive", "budget": 1})
    b_profile = client.get("/me/profile", headers=hb).json()

    assert b_profile["email"] == eb
    assert b_profile["risk_profile"] == "balanced"
    assert b_profile["budget"] is None


def test_dev_bypass_yalnizca_dev_ortaminda(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "auth_dev_bypass", True)

    monkeypatch.setattr(settings, "app_env", "prod")
    assert client.get("/me/profile").status_code == 401

    monkeypatch.setattr(settings, "app_env", "dev")
    r = client.get("/me/profile")
    assert r.status_code == 200
    assert r.json()["email"] == "dev@fontakip.local"


def test_ai_router_bagli_ve_giris_istiyor(client):
    """Kişi 3'ün router'ı /ai önekiyle (çift önek olmadan) bağlı ve auth'u kullanıyor."""
    paths = {route.path for route in client.app.routes}
    assert "/ai/chat" in paths and "/ai/chart-read" in paths
    assert "/ai/ai/chat" not in paths
    r = client.post("/ai/chat", json={"messages": [{"role": "user", "content": "RSI nedir?"}]})
    assert r.status_code == 401
