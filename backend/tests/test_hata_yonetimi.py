"""Hata yönetimi: beklenmeyen hata → JSON 500 (iç ayrıntı yok), veritabanı yok → 503 + Retry-After."""

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.main import app


@app.get("/_test/patla", include_in_schema=False)
def _patla():
    raise RuntimeError("gizli iç ayrıntı: şifre=123")


@app.get("/_test/db-yok", include_in_schema=False)
def _db_yok():
    raise OperationalError("SELECT 1", {}, Exception("connection refused"))


def test_beklenmeyen_hata_json_ve_sizinti_yok():
    c = TestClient(app, raise_server_exceptions=False)
    r = c.get("/_test/patla")
    assert r.status_code == 500
    assert r.json() == {"detail": "Beklenmeyen bir sunucu hatası oluştu."}
    assert "şifre" not in r.text


def test_veritabani_yoksa_503():
    c = TestClient(app, raise_server_exceptions=False)
    r = c.get("/_test/db-yok")
    assert r.status_code == 503 and r.headers["Retry-After"] == "30"
    assert "Veritabanına" in r.json()["detail"]
