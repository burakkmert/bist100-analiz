"""Sözlük araması (RAG'in "R"si).

Şimdilik saf Python BM25 kullanılır: bağımlılık yok, hızlı, 150–500 terim için fazlasıyla yeterli ve
Türkçe kısaltmalarda (RSI, F/K, TEFAS) gömme modellerinden daha isabetli. İleride gömme (embedding)
tabanlı arama eklenirse aynı `Retriever` arayüzüyle değiştirilir; çağıran kod değişmez.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from typing import Protocol, Sequence

from .glossary import Term, load_glossary

# Anlamsız sık kelimeler (aramaya katılmaz)
_STOP = set(
    "ve veya ile bir bu şu o ne nedir neden nasıl mi mı mu mü ki de da için gibi daha en çok az ama "
    "ise olan olarak bana beni sen siz ben biz var yok mudur midir anlamı anlama gelir demek ne demek "
    "açıklar açıkla mısın misin musun müsün merhaba selam nasılsın nasıl teşekkürler teşekkür sağol "
    "lütfen acaba peki tamam".split()
)
_STOP = {t.translate(str.maketrans("ıöüşçğ", "iouscg")) for t in _STOP}  # normalize edilmiş hâlleri


def normalize(text: str) -> str:
    """Türkçe küçük harf + aksan sadeleştirme (ı→i, ş→s ...) — kullanıcı aksansız yazsa da eşleşsin."""
    t = text.replace("I", "ı").replace("İ", "i").lower()
    t = t.translate(str.maketrans("ıöüşçğâîû", "iouscgaiu"))
    t = unicodedata.normalize("NFKD", t)
    return "".join(c for c in t if not unicodedata.combining(c))


def tokenize(text: str) -> list[str]:
    toks = re.findall(r"[a-z0-9]+(?:/[a-z0-9]+)?", normalize(text))
    out = []
    for tok in toks:
        if tok in _STOP or len(tok) < 2 and not tok.isdigit():
            continue
        out.append(tok)
        # Türkçe ekleri kabaca at: "hisseleri", "volatilitesi" → kök eşleşmesi için 5 harflik önek de ekle
        if len(tok) > 6 and tok[:5] not in _STOP:
            out.append(tok[:5])
    return out


class Retriever(Protocol):
    def search(self, query: str, k: int = 3) -> list[tuple[Term, float]]: ...


class BM25Retriever:
    def __init__(self, terms: Sequence[Term] | None = None, k1: float = 1.4, b: float = 0.6):
        self.terms = list(terms if terms is not None else load_glossary())
        self.k1, self.b = k1, b
        # Ad ve eş anlamlılar 3 kat ağırlıklı: kullanıcı çoğunlukla terimin adını sorar
        self.docs = [
            tokenize(" ".join([t.name] * 3 + list(t.aliases) * 3 + [t.definition, t.where])) for t in self.terms
        ]
        self.tf = [Counter(d) for d in self.docs]
        self.avgdl = sum(len(d) for d in self.docs) / max(1, len(self.docs))
        df = Counter(tok for d in self.docs for tok in set(d))
        n = len(self.docs)
        self.idf = {tok: math.log(1 + (n - f + 0.5) / (f + 0.5)) for tok, f in df.items()}
        self.alias_index = {normalize(a): i for i, t in enumerate(self.terms) for a in (t.name, *t.aliases)}

    def search(self, query: str, k: int = 3) -> list[tuple[Term, float]]:
        q = tokenize(query)
        nq = normalize(query)
        scores = [0.0] * len(self.terms)
        for i, tf in enumerate(self.tf):
            dl = len(self.docs[i])
            for tok in q:
                f = tf.get(tok)
                if not f:
                    continue
                idf = self.idf.get(tok, 0.0)
                scores[i] += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        # Sorguda bir eş anlamlı tam geçiyorsa güçlü bonus ("f/k nedir" → F/K oranı)
        for alias, i in self.alias_index.items():
            if len(alias) >= 2 and re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", nq):
                scores[i] += 8.0 + len(alias) * 0.2
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return [(self.terms[i], round(scores[i], 3)) for i in ranked[:k] if scores[i] > 3.0]


_default: BM25Retriever | None = None


def get_retriever() -> Retriever:
    global _default
    if _default is None:
        _default = BM25Retriever()
    return _default
