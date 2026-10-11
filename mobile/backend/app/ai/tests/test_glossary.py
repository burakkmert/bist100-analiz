from app.ai.glossary import load_glossary


def test_en_az_150_terim():
    assert len(load_glossary()) >= 150


def test_terim_adlari_benzersiz():
    names = [t.name for t in load_glossary()]
    assert len(names) == len(set(names))


def test_her_terimin_tum_alanlari_dolu():
    for t in load_glossary():
        assert t.aliases, t.name
        assert len(t.definition) > 30, t.name
        assert len(t.example) > 15, t.name
        assert t.where, t.name


def test_plandaki_zorunlu_terimler_var():
    names = " ".join(t.name.lower() for t in load_glossary())
    for must in ["rsi", "macd", "atr", "oynaklık", "stopaj", "temettü", "bedelsiz", "f/k", "kantil", "güven aralığı", "rejim"]:
        assert must in names, must
