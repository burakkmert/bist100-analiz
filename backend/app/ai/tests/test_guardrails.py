from app.ai import guardrails as g


def test_tavsiye_yakalanir():
    assert "advice" in g.violations("Bence hemen alın, fırsat kaçmasın.")
    assert "advice" in g.violations("Bu hisseyi almalısınız.")
    assert "advice" in g.violations("Al!")


def test_fiyat_hedefi_yakalanir():
    assert "price_claim" in g.violations("Hedef fiyat 350 olarak görülüyor.")
    assert "price_claim" in g.violations("Hisse 400 TL'ye çıkacak.")


def test_betimleyici_dil_serbest():
    ok = "Model 5 günlük ufukta yükseliş yönlü bir sinyal üretmiş; güven skoru 68."
    assert g.violations(ok) == []


def test_sanitize_ihlali_siler_ve_uyari_ekler():
    out = g.sanitize("RSI 72 ile aşırı alım bölgesinde. Hemen satın! Hedef fiyat 300.")
    assert "Hemen" not in out and "Hedef fiyat 300" not in out
    assert "RSI 72" in out
    assert g.DISCLAIMER in out


def test_sanitize_uyariyi_iki_kez_eklemez():
    once = g.sanitize("Açıklama.")
    assert g.sanitize(once).count(g.DISCLAIMER) == 1


def test_olumsuz_garanti_cumlesi_ihlal_degil():
    assert g.violations("Garanti getiri sunan bir fon yoktur; her yatırımın riski vardır.") == []
    assert g.violations("Garanti kazanç veremem.") == []
    assert "advice" in g.violations("Bu fon garanti getiri sağlar, kaçırmayın.")
