"""Gemini model sırası: gerçek ağa çıkmadan, sahte HTTP istemcisiyle test edilir."""
import asyncio
import sys
import types

# Testlerde httpx kurulu olmayabilir: yalnızca kullanılan parçaları taklit et
if "httpx" not in sys.modules:
    try:
        import httpx  # noqa: F401
    except ImportError:
        fake = types.ModuleType("httpx")

        class HTTPStatusError(Exception):
            def __init__(self, msg, request=None, response=None):
                super().__init__(msg)
                self.request, self.response = request, response

        fake.HTTPStatusError = HTTPStatusError
        fake.AsyncClient = lambda **kw: None
        fake.Timeout = lambda *a, **kw: None
        sys.modules["httpx"] = fake

import pytest

import app.ai.provider_openai as po


class Resp:
    def __init__(self, status, payload=None, text=""):
        self.status_code, self._payload, self.text, self.request = status, payload, text, None

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise po.httpx.HTTPStatusError("x", response=self)


OK = {"candidates": [{"content": {"parts": [{"text": "Merhaba"}]}}]}


class FakeClient:
    def __init__(self, plan):
        self.plan, self.calls = plan, []

    async def post(self, url, json=None, timeout=None):
        model = url.split("/models/")[1].split(":")[0]
        self.calls.append(model)
        r = self.plan[model]
        if isinstance(r, BaseException):
            raise r
        return r


def make(monkeypatch, models, plan):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setenv("GEMINI_MODEL", models)
    po._GEMINI_COOLDOWN.clear()
    p = po.GeminiProvider()
    p._client = FakeClient(plan)
    return p


def test_kota_dolunca_siradaki_model(monkeypatch):
    p = make(monkeypatch, "a,b,c", {"a": Resp(429, text="GenerateRequestsPerDayPerProjectPerModel"), "b": Resp(200, OK)})
    assert asyncio.run(p.complete("s", [{"role": "user", "content": "x"}])) == "Merhaba"
    assert p._client.calls == ["a", "b"] and p.last_model == "b"


def test_kotasi_dolan_model_sonra_atlanir(monkeypatch):
    p = make(monkeypatch, "a,b", {"a": Resp(429, text="PerDay"), "b": Resp(200, OK)})
    asyncio.run(p.complete("s", [{"role": "user", "content": "x"}]))
    p._client.calls.clear()
    asyncio.run(p.complete("s", [{"role": "user", "content": "x"}]))
    assert p._client.calls == ["b"]  # a artık denenmiyor


def test_hepsi_doluysa_hata_429_ile_doner(monkeypatch):
    p = make(monkeypatch, "a,b", {"a": Resp(429), "b": Resp(429)})
    with pytest.raises(po.httpx.HTTPStatusError) as e:
        asyncio.run(p.complete("s", [{"role": "user", "content": "x"}]))
    assert e.value.response.status_code == 429  # router "kullanım sınırı" mesajını gösterir


def test_400_gibi_hatalar_model_degistirmez(monkeypatch):
    p = make(monkeypatch, "a,b", {"a": Resp(400), "b": Resp(200, OK)})
    with pytest.raises(po.httpx.HTTPStatusError):
        asyncio.run(p.complete("s", [{"role": "user", "content": "x"}]))
    assert p._client.calls == ["a"]


def test_model_listesi_ayristirma():
    assert po._parse_models(" a, b ,a,, c ", "z") == ["a", "b", "c"]
    assert po._parse_models(None, "z") == ["z"]


def test_zaman_asiminda_siradaki_model(monkeypatch):
    """Görselli istekte takılan model beklenmez; sıradakine geçilir (telefon 'ulaşılamadı' demesin)."""
    p = make(monkeypatch, "a,b", {"a": TimeoutError("yavaş"), "b": Resp(200, OK)})
    assert asyncio.run(p.complete("s", [{"role": "user", "content": "x"}], images=[b"x"])) == "Merhaba"
    assert p._client.calls == ["a", "b"]


def test_hepsi_zaman_asimina_ugrarsa_timeout_hatasi(monkeypatch):
    p = make(monkeypatch, "a,b", {"a": TimeoutError(), "b": TimeoutError()})
    with pytest.raises(TimeoutError):
        asyncio.run(p.complete("s", [{"role": "user", "content": "x"}]))


def test_toplam_sure_dolunca_denemeyi_keser(monkeypatch):
    monkeypatch.setenv("GEMINI_TOTAL_TIMEOUT", "1")  # 5 sn'den az kaldıysa hiç denenmez
    p = make(monkeypatch, "a", {"a": Resp(200, OK)})
    with pytest.raises(TimeoutError):
        asyncio.run(p.complete("s", [{"role": "user", "content": "x"}]))
    assert p._client.calls == []


def test_router_hata_mesajlari():
    pytest.importorskip("fastapi")
    from app.ai.router import friendly_error

    class E(Exception):
        def __init__(self, status):
            self.response = type("R", (), {"status_code": status})()

    assert friendly_error(TimeoutError())[0] == 504
    assert friendly_error(E(429))[0] == 429
    assert friendly_error(E(503))[0] == 503
    assert "anahtar" in friendly_error(E(403))[1]
