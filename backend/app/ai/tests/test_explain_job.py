import asyncio

from app.ai.explain_job import Target, run_job, template_text, unknown_numbers, validate
from app.ai.provider import FakeProvider

A = {
    "code": "THYAO", "horizon": 5, "direction": "up", "confidence": 68, "risk": "medium", "regime": "trend",
    "range": {"low": 298.2, "mid": 316.0, "high": 333.5}, "indicators": {"rsi": 58.2},
}


class Fixed(FakeProvider):
    def __init__(self, text):
        super().__init__()
        self.text = text
        self.calls = 0

    async def complete(self, system, messages, images=None):
        self.calls += 1
        return self.text


def test_sablon_sayilari_dogru_aktarir():
    t = template_text(A)
    assert "5 günlük" in t and "68/100" in t and "298,2 – 333,5" in t
    assert validate(t, A) is None  # kendi şablonumuz doğrulamadan geçmeli


def test_uydurma_sayi_yakalanir():
    assert unknown_numbers("Hedef 410 TL civarı.", A) == ["410"]
    assert unknown_numbers("Aralık 298,2 ile 333,5 arasında, RSI 58.", A) == []


def test_tavsiye_ve_uzunluk_reddedilir():
    assert "korkuluk" in validate("Modeller yükseliş bekliyor, güven 68. Hemen alın, fırsat kaçmasın arkadaşlar!", A)
    assert validate("Kısa.", A) == "çok kısa"


def test_yalniz_sinyalli_ve_izlenenler_llm_e_gider():
    p = Fixed("Modeller 5 günlük ufukta yükseliş yönünde uzlaşıyor; güven skoru 68. Aralık 298,2 – 333,5 arasında, oynaklık orta.")
    targets = [Target(A, has_signal=True), Target({**A, "code": "ASELS"}, watched=True), Target({**A, "code": "GSP"})]
    rows, rep = asyncio.run(run_job(targets, p, "2026-10-12", delay=0))
    assert p.calls == 2
    assert [r.source for r in rows] == ["llm", "llm", "template"]
    assert rep.llm == 2 and rep.template == 1


def test_uydurma_cevap_sablona_doner():
    p = Fixed("Modeller yükseliş bekliyor ve hisse 450 seviyesine kadar çıkabilir; güven 68 ile orta düzeyde bir görünüm var.")
    rows, rep = asyncio.run(run_job([Target(A, has_signal=True)], p, "2026-10-12", delay=0))
    assert rows[0].source == "template_fallback" and "450" in rows[0].reason
    assert "298,2" in rows[0].text


def test_saglayici_hatasi_isi_durdurmaz():
    class Boom(FakeProvider):
        async def complete(self, system, messages, images=None):
            raise RuntimeError("ağ yok")

    rows, rep = asyncio.run(run_job([Target(A, has_signal=True), Target({**A, "code": "X"})], Boom(), "d", delay=0))
    assert [r.source for r in rows] == ["template_fallback", "template"]


def test_gecici_503_tekrar_denenir():
    class Resp:
        status_code = 503

    class Err(Exception):
        response = Resp()

    class Flaky(FakeProvider):
        calls = 0

        async def complete(self, system, messages, images=None):
            Flaky.calls += 1
            if Flaky.calls == 1:
                raise Err()
            return "Modeller 5 günlük ufukta yükseliş yönünde uzlaşıyor; güven skoru 68. Aralık 298,2 – 333,5 arasında."

    import app.ai.explain_job as ej

    async def no_sleep(_):
        return None

    orig = ej.asyncio.sleep
    ej.asyncio.sleep = no_sleep
    try:
        rows, _ = asyncio.run(run_job([Target(A, has_signal=True)], Flaky(), "d", delay=0))
    finally:
        ej.asyncio.sleep = orig
    assert rows[0].source == "llm" and Flaky.calls == 2


# ---- Güven kalibrasyonu (Kişi 1: hisselerde ham güven isabeti ayırt etmiyor) ----------------------------

STOCK = {**A, "asset_type": "stock", "confidence": 92}
FUND_UP5 = {**A, "code": "GSP", "asset_type": "fund", "confidence": 82}


def test_hisse_sablonu_guclu_ifade_kullanmaz():
    t = template_text(STOCK)
    assert "büyük ölçüde" not in t and "zayıf" in t and "belirsizlik yüksek" in t
    assert validate(t, STOCK) is None


def test_fon_5g_yukari_sinyalde_guven_anlamli():
    t = template_text(FUND_UP5)
    assert "büyük ölçüde uzlaşıyor" in t and "82/100" in t
    assert validate(t, FUND_UP5) is None


def test_hissede_yuksek_guven_ifadesi_reddedilir():
    text = "Modeller 5 günlük ufukta yükseliş yönünde; güven 92 ile yüksek güvenli bir görünüm var, aralık 298,2 – 333,5."
    assert "güçlü güven" in validate(text, STOCK)
    assert validate(text, {**FUND_UP5, "confidence": 92}) is None  # fonda bu ufukta güven anlamlı


def test_gecmis_isabet_orani_kullanilir():
    a = {**STOCK, "hit_rate": 0.57}
    t = template_text(a)
    assert "%57" in t and validate(t, a) is None
