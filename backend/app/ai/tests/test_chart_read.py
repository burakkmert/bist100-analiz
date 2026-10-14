import asyncio
import base64

import pytest

from app.ai.chart_read import NO_DATA_NOTE, parse_chart_json, read_chart
from app.ai.context import StaticAnalysisSource
from app.ai.provider import FakeProvider

IMG = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff fake jpeg").decode()


def test_sema_zorlanir():
    out = parse_chart_json('```json\n{"trend":"yukarı","supports":["298,5", 285, "x"],"summary":"Yükselen kanal."}\n```')
    assert out["trend"] == "flat"  # geçersiz değer → güvenli varsayılan
    assert out["supports"] == [285.0, 298.5]
    assert out["resistances"] == []
    assert out["confidence_note"] == NO_DATA_NOTE


def test_json_yoksa_hata():
    with pytest.raises(ValueError):
        parse_chart_json("Grafik yükseliyor.")


def test_ozetteki_tavsiye_temizlenir():
    out = parse_chart_json('{"trend":"up","summary":"Kanal yukarı. Hemen alın!"}')
    assert "Hemen alın" not in out["summary"]


def test_fake_ile_uctan_uca():
    out = asyncio.run(read_chart(IMG, None, FakeProvider()))
    assert out["trend"] in ("up", "down", "flat")
    assert out["confidence_note"] == NO_DATA_NOTE


def test_veri_varsa_baglam_eklenir():
    seen = {}

    class Spy(FakeProvider):
        async def complete(self, system, messages, images=None):
            seen["system"] = system
            return '{"trend":"up","summary":"Yükseliş.","confidence_note":"Sayısal veriyle karşılaştırıldı."}'

    src = StaticAnalysisSource({}, {"THYAO": [{"close": 300.0}, {"close": 312.5}]})
    out = asyncio.run(read_chart(IMG, "thyao", Spy(), src))
    assert "son 312.5" in seen["system"] and "değişim %4.2" in seen["system"]
    assert out["confidence_note"] == "Sayısal veriyle karşılaştırıldı."


def test_fiyat_ozeti_destek_direnc_adaylari():
    from app.ai.context import price_summary

    # 100 ile 110 arasında gidip gelen fiyat: dipler ~100, tepeler ~110
    closes = [100, 102, 105, 108, 110, 108, 105, 102, 100, 102, 105, 108, 110, 108, 105, 102, 100, 103, 106, 109, 110, 107]
    out = price_summary([{"date": f"2026-01-{i + 1:02d}", "close": c} for i, c in enumerate(closes)])
    assert "Destek adayları" in out and "100" in out.split("Destek adayları")[1].split("\n")[0]
    assert "Direnç adayları" in out and "110" in out.split("Direnç adayları")[1].split("\n")[0]
    assert "20 günlük ortalama" in out
    assert price_summary([]) is None and price_summary([{"close": 1}]) is None
