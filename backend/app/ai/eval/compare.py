"""LLM sağlayıcı karşılaştırması (Görev 4 — tez tablosu).

Her sağlayıcıya aynı 20 Türkçe soru, uygulamadaki gerçek akışla (RAG + bağlam + korkuluk) sorulur.
Ölçülenler:
  • Doğruluk göstergesi: cevapta beklenen ifadelerden en az biri geçiyor mu (expect_any)
  • Korkuluk: modelin HAM cevabında al/sat ya da fiyat hedefi ihlali var mı (guardrails.violations)
  • Süre (saniye) ve cevap uzunluğu

Kullanım (backend/ klasöründen, .venv etkinken):
    python -m app.ai.eval.compare --providers gemini,fake
    python -m app.ai.eval.compare --providers gemini,ollama --out ../docs/kisi3/llm_karsilastirma.md

Not: Otomatik ölçüm kaba bir göstergedir; tezde Türkçe akıcılık ve doğruluk için cevapları elle de puanlayın
(betik her cevabı Markdown dosyasına yazar).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
from pathlib import Path

from .. import guardrails
from ..chat import ChatRequest, prepare
from ..context import StaticAnalysisSource
from ..provider import get_provider
from ..rag import get_retriever
from ..settings import load_env

HERE = Path(__file__).parent

# Bağlam sorularında kullanılan sabit analiz (uygulamadaki THYAO örneğiyle aynı sayılar)
DEMO_SOURCE = StaticAnalysisSource(
    {
        "THYAO": {
            "code": "THYAO", "asset_type": "stock", "horizon": 5, "direction": "up", "confidence": 68, "risk": "medium", "regime": "trend",
            "range": {"low": 298.2, "mid": 316.0, "high": 333.5},
            "indicators": {"rsi": 58.2, "macd_hist": 0.4, "ma20_above_ma50": True, "atr_pct": 2.1},
            "weights": {"timesfm": 0.6, "chronos": 0.4},
        }
    }
)


def _norm(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


async def ask(provider, q: dict) -> dict:
    req = ChatRequest(messages=[{"role": "user", "content": q["q"]}], context=q.get("context"))
    system, history, _ = await prepare(req, get_retriever(), DEMO_SOURCE)
    raw, err, dt = "", None, 0.0
    for attempt in range(4):  # geçici hatalarda tekrar dene
        t0 = time.perf_counter()
        try:
            raw = await provider.complete(system, history)
            err = None
            dt = time.perf_counter() - t0
            break
        except Exception as e:  # sağlayıcı hatası satırı bozmasın
            status = getattr(getattr(e, "response", None), "status_code", None)
            err = f"HTTP {status}" if status else f"{type(e).__name__}: {e}"[:200]
            timeout = "Timeout" in type(e).__name__
            if timeout and attempt < 3:
                await asyncio.sleep(5)  # model geç cevap verdi: bir kez daha dene
            elif status == 429 and attempt < 3:
                await asyncio.sleep(30 * (attempt + 1))  # dakika sınırı: kotanın dolmasını bekle
            elif status in (500, 502, 503, 504) and attempt < 3:
                await asyncio.sleep(6 * (attempt + 1))  # geçici yoğunluk
            else:
                break
    text = _norm(raw)
    return {
        "id": q["id"],
        "kind": q["kind"],
        "q": q["q"],
        "answer": raw,
        "error": err,
        "seconds": round(dt, 2),
        "chars": len(raw),
        "hit": bool(raw) and any(_norm(e) in text for e in q["expect_any"]),
        "violations": guardrails.violations(raw),
    }


async def run_provider(name: str, questions: list[dict], delay: float) -> list[dict]:
    provider = get_provider(name)
    rows = []
    for i, q in enumerate(questions):
        rows.append(await ask(provider, q))
        print(f"  [{name}] {i + 1:>2}/{len(questions)} {q['id']} {'✓' if rows[-1]['hit'] else '·'}"
              f"{' ⚠' if rows[-1]['violations'] else ''}{' HATA (' + rows[-1]['error'] + ')' if rows[-1]['error'] else ''}", flush=True)
        if delay:
            await asyncio.sleep(delay)  # ücretsiz katmanın dakika sınırına takılmamak için
    return rows


def summarize(name: str, rows: list[dict]) -> dict:
    ok = [r for r in rows if not r["error"]]
    adv = [r for r in rows if r["kind"] == "korkuluk"]
    return {
        "provider": name,
        "answered": f"{len(ok)}/{len(rows)}",
        "hit_rate": f"%{round(100 * sum(r['hit'] for r in rows) / len(rows))}",
        "hit_answered": f"%{round(100 * sum(r['hit'] for r in ok) / len(ok))}" if ok else "-",
        "violations": sum(bool(r["violations"]) for r in rows),
        "guard_ok": f"{sum(not r['violations'] and not r['error'] for r in adv)}/{len(adv)}",
        "errors": sorted({r["error"] for r in rows if r["error"]}),
        "median_s": round(statistics.median([r["seconds"] for r in ok]), 2) if ok else None,
        "avg_chars": round(statistics.mean([r["chars"] for r in ok])) if ok else None,
    }


def to_markdown(summaries: list[dict], results: dict[str, list[dict]]) -> str:
    lines = [
        "# LLM sağlayıcı karşılaştırması",
        "",
        "Aynı 20 Türkçe soru, uygulamadaki gerçek akışla (sözlük araması + ekran bağlamı + sistem istemi) soruldu.",
        "",
        "| Sağlayıcı | Cevaplanan | Beklenen bilgi (tümü) | Beklenen bilgi (cevaplananlar) | Korkuluk ihlali (ham) | Kışkırtıcı sorularda doğru davranış | Medyan süre (sn) | Ort. uzunluk |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in summaries:
        lines.append(
            f"| {s['provider']} | {s['answered']} | {s['hit_rate']} | {s['hit_answered']} | {s['violations']} | {s['guard_ok']} | {s['median_s']} | {s['avg_chars']} |"
        )
        if s["errors"]:
            lines.append(f"| ↳ {s['provider']} hataları: {', '.join(s['errors'])} | | | | | | | |")
    lines += ["", "Ham ihlaller uygulamada guardrails.sanitize ile ayrıca temizlenir; tablo modelin kendi eğilimini gösterir.", ""]
    for name, rows in results.items():
        lines += [f"## {name} — cevaplar", ""]
        for r in rows:
            mark = "✓" if r["hit"] else "✗"
            warn = f" ⚠ {', '.join(r['violations'])}" if r["violations"] else ""
            lines += [f"**{r['id']} ({r['kind']}) {mark}{warn}** — {r['q']}  ", f"_{r['seconds']} sn_", ""]
            lines += [f"> {r['error']}" if r["error"] else "> " + r["answer"].strip().replace("\n", "\n> "), ""]
    return "\n".join(lines)


def main() -> None:
    load_env()  # backend/.env (LLM_PROVIDER, GEMINI_API_KEY ...)
    ap = argparse.ArgumentParser(description="LLM sağlayıcı karşılaştırması")
    ap.add_argument("--providers", default="fake", help="virgülle: gemini,ollama,deepseek,fake")
    ap.add_argument("--out", default=str(HERE / "sonuc.md"))
    ap.add_argument("--delay", type=float, default=float(os.getenv("EVAL_DELAY", "4")), help="sorular arası bekleme (sn)")
    ap.add_argument("--limit", type=int, default=0, help="yalnızca ilk N soru (hızlı deneme)")
    ap.add_argument("--only", default="", help="yalnızca bu soru kimlikleri, virgülle (ör. q01,q14)")
    args = ap.parse_args()

    questions = json.loads((HERE / "questions.json").read_text(encoding="utf-8"))
    if args.only:
        wanted = {x.strip() for x in args.only.split(",")}
        questions = [q for q in questions if q["id"] in wanted]
    if args.limit:
        questions = questions[: args.limit]

    results: dict[str, list[dict]] = {}
    for name in [p.strip() for p in args.providers.split(",") if p.strip()]:
        print(f"→ {name}")
        results[name] = asyncio.run(run_provider(name, questions, 0 if name == "fake" else args.delay))

    summaries = [summarize(n, r) for n, r in results.items()]
    Path(args.out).write_text(to_markdown(summaries, results), encoding="utf-8")
    (Path(args.out).with_suffix(".json")).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + "\n".join(l for l in to_markdown(summaries, {}).splitlines() if l.startswith("|")))
    print(f"\nAyrıntılar: {args.out}")


if __name__ == "__main__":
    main()
