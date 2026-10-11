from app.ai.rag import get_retriever, normalize


def top(q):
    res = get_retriever().search(q, k=3)
    return res[0][0].name if res else None


def test_kisaltmalar():
    assert top("RSI nedir?").startswith("RSI")
    assert top("f/k oranı ne anlatıyor") == "F/K oranı"
    assert top("tefas") == "TEFAS"


def test_aksansiz_yazim():
    assert top("temettu nedir") == "Temettü"
    assert normalize("İŞLEM Günü") == "islem gunu"


def test_uygulama_dili():
    assert top("mavi koni ne") == "Tahmin bandı"
    assert top("güven skoru ne anlama geliyor") == "Güven skoru"
    assert top("stop loss") == "Zarar kes"


def test_alakasiz_soruda_madde_yok():
    assert get_retriever().search("merhaba nasılsın") == []
