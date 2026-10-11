"""Cevap korkulukları (sistem istemine ek, ikinci savunma hattı).

LLM ne kadar iyi yönlendirilirse yönlendirilsin bazen emir kipiyle "al/sat" diyebilir ya da
kendi fiyat hedefini uydurabilir. Bu modül cevabı istemciye gitmeden önce kontrol eder.
"""
from __future__ import annotations

import re

DISCLAIMER = "Bu bir model yorumudur, yatırım tavsiyesi değildir."

# Emir kipi / doğrudan tavsiye kalıpları
_W = r"(?<![\w])"  # kelime başı (Türkçe harflerle de çalışır)
_ADVICE = re.compile(
    "|".join(
        [
            _W + r"(hemen|kesinlikle|mutlaka|şimdi)\s+(al|sat|alın|satın|alınız|satınız)(?![\w])",
            _W + r"(almalısın(ız)?|satmalısın(ız)?|almanı(zı)? öneririm|satmanı(zı)? öneririm)(?![\w])",
            _W + r"(al(ın)?|sat(ın)?)\s*!",
            _W + r"alım fırsatı(nı)? kaçırma(yın)?",
            _W + r"garanti(li)? (kazanç|getiri)",
        ]
    ),
    re.IGNORECASE,
)

# "hedef fiyat 350", "350 TL'ye çıkacak" gibi uydurma tahminler
_PRICE_CLAIM = re.compile(
    r"(hedef fiyat(ı)?\s*[:\-]?\s*\d)|(\d[\d.,]*\s*(tl|₺)['’]?(ye|ya|e|a)\s+(çıkacak|düşecek|ulaşacak))",
    re.IGNORECASE,
)


def violations(text: str) -> list[str]:
    found = []
    if _ADVICE.search(text):
        found.append("advice")
    if _PRICE_CLAIM.search(text):
        found.append("price_claim")
    return found


def sanitize(text: str) -> str:
    """İhlal varsa ilgili cümleleri yumuşatır; her durumda uyarı satırını garanti eder."""
    out = text
    if _ADVICE.search(out) or _PRICE_CLAIM.search(out):
        sentences = re.split(r"(?<=[.!?])\s+", out)
        kept = [s for s in sentences if not (_ADVICE.search(s) or _PRICE_CLAIM.search(s))]
        out = " ".join(kept).strip()
        note = "Al/sat kararı ya da fiyat hedefi veremem; modelin verdiği olasılık aralığını yorumlayabilirim."
        out = f"{out}\n\n{note}" if out else note
    if DISCLAIMER not in out:
        out = f"{out.rstrip()}\n\n{DISCLAIMER}"
    return out
