import asyncio
import base64

import pytest

from app.ai.chat import ChatRequest, build_system, chat_once, chat_stream, decode_image, prepare
from app.ai.context import StaticAnalysisSource
from app.ai.guardrails import DISCLAIMER
from app.ai.provider import FakeProvider, get_provider
from app.ai.rag import get_retriever

THYAO = {
    "code": "THYAO", "horizon": 5, "direction": "up", "confidence": 68, "risk": "medium", "regime": "trend",
    "range": {"low": 298.2, "mid": 316.0, "high": 333.5},
    "indicators": {"rsi": 58.2, "macd_hist": 0.4}, "weights": {"timesfm": 0.6, "chronos": 0.4},
}


def run(coro):
    return asyncio.run(coro)


def test_varsayilan_saglayici_fake():
    assert get_provider().name == "fake"
    with pytest.raises(ValueError):
        get_provider("yok-boyle-bir-model")


def test_sistem_istemi_korkuluklari_icerir():
    s = build_system("bağlam", ["[RSI]\nTanım: x"])
    assert "Yatırım tavsiyesi verme" in s
    assert "### EKRAN BAĞLAMI" in s and "### İLGİLİ SÖZLÜK MADDELERİ" in s


def test_rag_ve_baglam_isteme_eklenir():
    req = ChatRequest(
        messages=[{"role": "user", "content": "RSI ne demek?"}],
        context={"screen": "asset_detail", "code": "thyao", "horizon": 5},
    )
    system, history, sources = run(prepare(req, get_retriever(), StaticAnalysisSource({"THYAO": THYAO})))
    assert sources[0].startswith("RSI")
    assert "Varlık: thyao" in system or "Varlık: THYAO" in system
    assert "Güven skoru: 68/100" in system
    assert "298.2 – 333.5" in system  # sayılar değiştirilmeden aktarılır


def test_veri_yoksa_uydurma_uyarisi():
    req = ChatRequest(messages=[{"role": "user", "content": "Bu sinyal neden geldi?"}], context={"screen": "asset_detail", "code": "ASELS"})
    system, _, _ = run(prepare(req, get_retriever(), StaticAnalysisSource({})))
    assert "veri yok" in system


def test_akis_parcalari_ve_bitis():
    req = ChatRequest(messages=[{"role": "user", "content": "RSI nedir?"}])
    events = run(_collect(chat_stream(req, FakeProvider(), get_retriever())))
    assert len([e for e in events if e.delta]) > 3  # kelime kelime
    assert events[-1].done and events[-1].sources
    text = "".join(e.delta for e in events)
    assert "RSI" in text and DISCLAIMER in text


def test_ihlalli_cevap_degistirilir():
    class Bad(FakeProvider):
        async def complete(self, system, messages, images=None):
            return "Yükseliş bekleniyor. Hemen alın!"

    out = run(chat_once(ChatRequest(messages=[{"role": "user", "content": "alayım mı"}]), Bad(), get_retriever()))
    assert "Hemen alın" not in out
    assert DISCLAIMER in out


def test_son_mesaj_kullanicidan_olmali():
    with pytest.raises(ValueError):
        run(chat_once(ChatRequest(messages=[{"role": "assistant", "content": "selam"}]), FakeProvider(), get_retriever()))


def test_gorsel_dogrulama():
    png = "data:image/png;base64," + base64.b64encode(b"\x89PNG....").decode()
    assert decode_image(png).startswith(b"\x89PNG")
    with pytest.raises(ValueError):
        decode_image("http://ornek.com/a.png")


async def _collect(agen):
    return [e async for e in agen]
