"""Gece uzman yorumları (Görev 9) — saat 22:00'de gece işi orkestrasyonu tarafından çağrılır.

Her varlığın analysis satırı için 2–3 cümlelik Türkçe yorum üretir ve ai_explanations tablosuna yazar.
Maliyet ve ücretsiz kota için:
  • Yalnızca sinyali olan ya da en az bir kullanıcının izlediği varlıklar LLM'e gider.
  • Diğerlerine kurallı şablon metin yazılır (LLM çağrısı yok).
Halüsinasyona karşı: LLM metninde analizde olmayan bir sayı geçerse ya da korkuluk ihlali varsa
o yorum reddedilir ve şablon kullanılır.

Kişi 2 için: veritabanı bağlanınca `ExplainSource` ve `ExplanationSink`'in DB sürümleri yazılır
(analysis/signals/watchlist tablolarından okuyup ai_explanations'a upsert). Şimdilik JSON dosyalarıyla çalışır.

Elle çalıştırma (backend/ klasöründen):
    python -m app.ai.explain_job --input app/ai/samples/analyses.json --out explanations.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Protocol

from . import guardrails
from .chat import load_prompt
from .context import describe
from .provider import LLMProvider, get_provider
from .settings import load_env

log = logging.getLogger("app.ai.explain")

MAX_CHARS = 600


# ---- Veri sözleşmeleri ------------------------------------------------------------------------------


@dataclass
class Target:
    """Yorum yazılacak bir (varlık, ufuk) satırı."""

    analysis: dict[str, Any]
    has_signal: bool = False
    watched: bool = False

    @property
    def code(self) -> str:
        return str(self.analysis["code"]).upper()

    @property
    def horizon(self) -> int:
        return int(self.analysis.get("horizon") or 5)

    @property
    def use_llm(self) -> bool:
        return self.has_signal or self.watched


@dataclass
class Explanation:
    """ai_explanations satırı (code, run_date, horizon, text) + izleme alanları."""

    code: str
    run_date: str
    horizon: int
    text: str
    source: str  # "llm" | "template" | "template_fallback"
    reason: str | None = None


class ExplainSource(Protocol):
    def targets(self) -> Iterable[Target]: ...


class ExplanationSink(Protocol):
    def save(self, rows: list[Explanation]) -> None: ...


# ---- Şablon metin (LLM'siz) -----------------------------------------------------------------------------

_DIR = {"up": "yükseliş", "down": "düşüş", "flat": "yatay seyir"}
_RISK = {"low": "düşük", "medium": "orta", "high": "yüksek"}
# Sözleşme v0.2 (shared/openapi.yaml → Regime): trend | range | high_vol
_REGIME = {"trend": "belirgin bir trend", "range": "yatay bir piyasa", "high_vol": "oynak bir piyasa"}


def _fmt(v: Any) -> str:
    """Türkçe ondalık: 298.2 → 298,2 (tam sayılar olduğu gibi)."""
    if isinstance(v, (int, float)):
        s = f"{v:.2f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)
        return s.replace(".", ",")
    return str(v)


def template_text(a: dict[str, Any]) -> str:
    h = a.get("horizon", 5)
    conf = a.get("confidence")
    d = _DIR.get(a.get("direction", ""), "belirsiz")
    agree = "büyük ölçüde uzlaşıyor" if isinstance(conf, (int, float)) and conf >= 65 else "kısmen ayrışıyor"
    r = a.get("range") or {}
    parts = [f"Modeller {h} günlük ufukta {d} yönünde {agree} (güven {conf}/100)."]
    if r.get("low") is not None and r.get("high") is not None:
        parts.append(f"Fiyatın bu sürede %80 olasılıkla {_fmt(r['low'])} – {_fmt(r['high'])} aralığında kalması bekleniyor.")
    tail = []
    if a.get("risk") in _RISK:
        tail.append(f"oynaklık {_RISK[a['risk']]}")
    if a.get("regime") in _REGIME:
        tail.append(f"piyasa {_REGIME[a['regime']]} görünümünde")
    if tail:
        parts.append(" ve ".join(tail).capitalize() + ".")
    return " ".join(parts)


# ---- Doğrulama -------------------------------------------------------------------------------------------

_NUM = re.compile(r"(?<![\w])\d+(?:[.,]\d+)?")


def _numbers_in(obj: Any) -> set[float]:
    out: set[float] = set()
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        out.add(round(float(obj), 2))
    elif isinstance(obj, dict):
        for v in obj.values():
            out |= _numbers_in(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out |= _numbers_in(v)
    return out


def unknown_numbers(text: str, analysis: dict[str, Any]) -> list[str]:
    """Metinde geçip analizde (makul yuvarlamayla) karşılığı olmayan sayılar."""
    allowed = _numbers_in(analysis) | {80.0, 10.0, 90.0, 50.0, 100.0}  # %80 aralık, p10/p90, /100 gibi sabitler
    bad = []
    for m in _NUM.findall(text):
        v = float(m.replace(",", "."))
        # 1–9 arası küçük tam sayılar (ör. "2–3 gün", "iki model") ve ufuklar serbest
        if v.is_integer() and v <= 20:
            continue
        if not any(abs(v - a) <= max(0.51, abs(a) * 0.005) for a in allowed):
            bad.append(m)
    return bad


def validate(text: str, analysis: dict[str, Any]) -> str | None:
    """Sorun yoksa None, varsa ret sebebi."""
    t = text.strip()
    if len(t) < 40:
        return "çok kısa"
    if len(t) > MAX_CHARS:
        return "çok uzun"
    if guardrails.violations(t):
        return "korkuluk ihlali: " + ",".join(guardrails.violations(t))
    bad = unknown_numbers(t, analysis)
    if bad:
        return "analizde olmayan sayı: " + ", ".join(bad[:3])
    return None


# ---- İş --------------------------------------------------------------------------------------------------


async def _llm_text(provider: LLMProvider, system: str, a: dict[str, Any], retries: int, backoff: float) -> str:
    ctx = describe({"screen": "asset_detail", "code": a["code"]}, a)
    msg = [{"role": "user", "content": f"Analiz:\n{ctx}\n\nBu analiz için yorumu yaz."}]
    for attempt in range(retries + 1):
        try:
            return (await provider.complete(system, msg)).strip()
        except Exception as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if attempt < retries and status == 429:  # dakika sınırı: uzun bekle
                await asyncio.sleep(backoff * (attempt + 1))
                continue
            if attempt < retries and status in (500, 502, 503, 504):  # sağlayıcı geçici yoğun: kısa bekle
                await asyncio.sleep(5 * (attempt + 1))
                continue
            raise
    return ""


@dataclass
class JobReport:
    run_date: str
    total: int = 0
    llm: int = 0
    template: int = 0
    fallback: int = 0
    seconds: float = 0.0
    fallback_reasons: list[str] = field(default_factory=list)


async def run_job(
    targets: Iterable[Target],
    provider: LLMProvider,
    run_date: str,
    *,
    delay: float = 4.0,
    max_llm: int = 200,
    retries: int = 2,
    backoff: float = 20.0,
) -> tuple[list[Explanation], JobReport]:
    system = load_prompt("system_explain")
    report = JobReport(run_date=run_date)
    rows: list[Explanation] = []
    t0 = time.perf_counter()
    llm_calls = 0

    for t in targets:
        a = t.analysis
        report.total += 1
        base = dict(code=t.code, run_date=run_date, horizon=t.horizon)

        if not t.use_llm or llm_calls >= max_llm:
            rows.append(Explanation(**base, text=template_text(a), source="template"))
            report.template += 1
            continue

        llm_calls += 1
        reason: str | None
        try:
            text = await _llm_text(provider, system, a, retries, backoff)
            reason = validate(text, a)
        except Exception as e:
            text, reason = "", f"sağlayıcı hatası: {type(e).__name__}"

        if reason is None:
            rows.append(Explanation(**base, text=text, source="llm"))
            report.llm += 1
        else:
            log.warning("%s/%s yorum reddedildi (%s)", t.code, t.horizon, reason)
            rows.append(Explanation(**base, text=template_text(a), source="template_fallback", reason=reason))
            report.fallback += 1
            report.fallback_reasons.append(f"{t.code}/{t.horizon}: {reason}")
        if delay:
            await asyncio.sleep(delay)

    report.seconds = round(time.perf_counter() - t0, 1)
    return rows, report


# ---- Dosya tabanlı kaynak/hedef (DB hazır olana kadar) -----------------------------------------------------


class JsonSource:
    """[{ "analysis": {...}, "has_signal": true, "watched": false }, ...] biçimli dosya."""

    def __init__(self, path: Path):
        self.items = json.loads(Path(path).read_text(encoding="utf-8"))

    def targets(self) -> Iterable[Target]:
        for it in self.items:
            yield Target(analysis=it["analysis"], has_signal=bool(it.get("has_signal")), watched=bool(it.get("watched")))


class JsonSink:
    def __init__(self, path: Path):
        self.path = Path(path)

    def save(self, rows: list[Explanation]) -> None:
        self.path.write_text(json.dumps([asdict(r) for r in rows], ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    load_env()  # backend/.env (LLM_PROVIDER, GEMINI_API_KEY ...)
    ap = argparse.ArgumentParser(description="Gece uzman yorumları")
    ap.add_argument("--input", default=str(Path(__file__).parent / "samples" / "analyses.json"))
    ap.add_argument("--out", default="explanations.json")
    ap.add_argument("--provider", default=None, help="varsayılan: LLM_PROVIDER")
    ap.add_argument("--run-date", default=time.strftime("%Y-%m-%d"))
    ap.add_argument("--delay", type=float, default=4.0, help="LLM çağrıları arası bekleme (sn)")
    ap.add_argument("--max-llm", type=int, default=200, help="bir gecede en fazla LLM çağrısı")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    provider = get_provider(args.provider)
    rows, rep = asyncio.run(
        run_job(JsonSource(Path(args.input)).targets(), provider, args.run_date, delay=0 if provider.name == "fake" else args.delay, max_llm=args.max_llm)
    )
    JsonSink(Path(args.out)).save(rows)
    print(f"{rep.total} varlık · LLM {rep.llm} · şablon {rep.template} · reddedilip şablona dönen {rep.fallback} · {rep.seconds} sn")
    for r in rep.fallback_reasons:
        print("  ↳", r)
    print(f"Yazıldı: {args.out}")


if __name__ == "__main__":
    main()
