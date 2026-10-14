"""Grafik okuma değerlendirmesi (Görev 7 — tez tablosu).

Doğru cevabı bilinen sentetik grafikler üretir, uygulamadaki gerçek akışla (read_chart) yorumlatır ve puanlar:
  • Trend doğruluğu: yükselen / düşen / yatay — grafik bu eğilimle üretildiği için doğru cevap bellidir.
  • Seviye isabeti (yatay grafikler): fiyat bilinen bir destek ile direnç arasında gidip gelir; modelin verdiği
    seviyelerden biri gerçeğe %3'ten yakınsa isabet sayılır.
  • Makullük: verilen tüm destek/direnç sayıları grafiğin fiyat aralığında mı (uydurma sayı göstergesi).
İki koşul karşılaştırılır:
  • image  → yalnızca görüntü (kullanıcı başka uygulamadan ekran görüntüsü yüklemiş gibi)
  • data   → görüntü + son 120 günün sayısal özeti (uygulama içi "Yorumla" düğmesi gibi)

Ücretsiz kota (model başına günde ~20 istek) için sonuçlar her istekten sonra JSONL dosyasına eklenir;
betik yeniden çalıştırılınca yapılanları atlar ve kaldığı yerden devam eder. Birkaç güne yayılabilir.

Kullanım (backend/ klasöründen, .venv etkinken; ilk seferde: pip install matplotlib):
    python -m app.ai.eval.chart_eval --n 50 --mode both --delay 8
    python -m app.ai.eval.chart_eval --report            # yalnızca rapor (yeni istek atmaz)
Çıktılar: grafik_eval/sonuc.jsonl, grafik_eval/rapor.md, grafik_eval/img/*.png
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import math
import random
import time
from pathlib import Path

from ..chart_read import read_chart
from ..context import StaticAnalysisSource
from ..provider import get_provider
from ..settings import load_env

TRENDS = ("up", "down", "flat")
TREND_TR = {"up": "yükselen", "down": "düşen", "flat": "yatay"}
DAYS = 120
LEVEL_TOL = 0.03


# ---- Sentetik grafik ---------------------------------------------------------------------------------


def make_series(i: int) -> dict:
    """i. örnek: trend sırayla up/down/flat; fiyat düzeyi, oynaklık ve şekil tohumdan rastgele."""
    rng = random.Random(1000 + i)
    trend = TRENDS[i % 3]
    base = rng.choice([8, 25, 60, 140, 320])
    vol = rng.uniform(0.008, 0.018)
    closes: list[float] = []
    truth: dict = {"trend": trend}
    if trend == "flat":
        # Bilinen bant: destek S ile direnç R arasında 2–4 kez gidip gelir
        width = rng.uniform(0.08, 0.16)
        s, r = base * (1 - width / 2), base * (1 + width / 2)
        cycles = rng.uniform(2.0, 4.0)
        phase = rng.uniform(0, 2 * math.pi)
        for d in range(DAYS):
            mid = (s + r) / 2 + (r - s) / 2 * 0.92 * math.sin(2 * math.pi * cycles * d / DAYS + phase)
            closes.append(mid * (1 + rng.gauss(0, vol * 0.35)))
        truth.update(support=round(s, 2), resistance=round(r, 2))
    else:
        total = rng.uniform(0.25, 0.45) * (1 if trend == "up" else -1)  # 120 günde %25–45
        step = math.log(1 + total) / DAYS
        p = base
        for _ in range(DAYS):
            p *= math.exp(step + rng.gauss(0, vol))
            closes.append(p)
    dates = [f"D{d + 1}" for d in range(DAYS)]
    return {"id": f"G{i + 1:02d}", "trend": trend, "closes": [round(c, 4) for c in closes], "dates": dates, "truth": truth}


def render_png(sample: dict, path: Path) -> bytes:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=100)
    ax.plot(range(DAYS), sample["closes"], color="#2F5BEA", linewidth=1.6)
    ax.set_title(f"Örnek {sample['id']} — günlük kapanış (son {DAYS} gün)")
    ax.set_xlabel("gün")
    ax.yaxis.tick_right()
    ax.grid(alpha=0.25)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, format="png")
    plt.close(fig)
    return path.read_bytes()


# ---- Puanlama ----------------------------------------------------------------------------------------


def score(sample: dict, out: dict) -> dict:
    lo, hi = min(sample["closes"]), max(sample["closes"])
    levels = list(out.get("supports") or []) + list(out.get("resistances") or [])
    in_range = [lo * 0.95 <= v <= hi * 1.05 for v in levels]
    res = {
        "trend_ok": out.get("trend") == sample["trend"],
        "levels": len(levels),
        "levels_plausible": sum(in_range),
    }
    t = sample["truth"]
    if sample["trend"] == "flat":
        near = lambda xs, target: any(abs(v - target) / target <= LEVEL_TOL for v in xs)  # noqa: E731
        res["support_hit"] = near(out.get("supports") or [], t["support"])
        res["resistance_hit"] = near(out.get("resistances") or [], t["resistance"])
    return res


# ---- Çalıştırma --------------------------------------------------------------------------------------


async def run_one(provider, sample: dict, mode: str, img: bytes, retries: int = 3) -> dict:
    uri = "data:image/png;base64," + base64.b64encode(img).decode()
    code, source = None, None
    if mode == "data":
        code = sample["id"]
        prices = [{"date": d, "close": c} for d, c in zip(sample["dates"], sample["closes"], strict=True)]
        source = StaticAnalysisSource({}, {code: prices})
    err, out, dt = None, None, 0.0
    for attempt in range(retries + 1):
        t0 = time.perf_counter()
        try:
            out = await read_chart(uri, code, provider, source)
            err = None
            dt = time.perf_counter() - t0
            break
        except Exception as e:  # kota/yoğunluk: biraz bekle, tekrar dene
            dt = time.perf_counter() - t0
            err = f"{type(e).__name__}: {e}"[:200]
            status = getattr(getattr(e, "response", None), "status_code", None)
            if attempt < retries and (status in (429, 500, 502, 503, 504) or "Timeout" in type(e).__name__):
                await asyncio.sleep(20 * (attempt + 1))
                continue
            break
    row = {"id": sample["id"], "mode": mode, "trend": sample["trend"], "seconds": round(dt, 1),
           "provider": provider.name, "model": getattr(provider, "last_model", None)}
    if out is None:
        row["error"] = err
    else:
        row["out"] = out
        row.update(score(sample, out))
    return row


def load_done(path: Path) -> dict[tuple[str, str], dict]:
    done = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if "error" not in r:  # hatalılar yeniden denenir
                    done[(r["id"], r["mode"])] = r
    return done


def pct(a: int, b: int) -> str:
    return f"%{100 * a / b:.0f} ({a}/{b})" if b else "—"


def report(rows: list[dict], n: int) -> str:
    lines = ["# Grafik okuma değerlendirmesi", "",
             f"Sentetik {n} grafik (her biri yükselen / düşen / yatay, doğru cevap üretimden bilinir). "
             "Seviye isabeti: yatay grafiklerde verilen destek/direnç gerçeğe %3'ten yakın mı. "
             "Makullük: verilen seviyeler grafiğin fiyat aralığında mı.", ""]
    modes = [m for m in ("image", "data") if any(r["mode"] == m for r in rows)]
    lines += ["| Koşul | Örnek | Trend doğruluğu | Destek isabeti (yatay) | Direnç isabeti (yatay) | Makul seviye oranı | Ort. süre |",
              "|---|---|---|---|---|---|---|"]
    for m in modes:
        rs = [r for r in rows if r["mode"] == m]
        flat = [r for r in rs if r["trend"] == "flat"]
        lv = sum(r["levels"] for r in rs)
        name = "Yalnızca görüntü" if m == "image" else "Görüntü + 120 günlük veri"
        lines.append(
            f"| {name} | {len(rs)} | {pct(sum(r['trend_ok'] for r in rs), len(rs))} | "
            f"{pct(sum(r.get('support_hit', False) for r in flat), len(flat))} | "
            f"{pct(sum(r.get('resistance_hit', False) for r in flat), len(flat))} | "
            f"{pct(sum(r['levels_plausible'] for r in rs), lv)} | "
            f"{(sum(r['seconds'] for r in rs) / len(rs)) if rs else 0:.1f} sn |")
    for m in modes:
        rs = [r for r in rows if r["mode"] == m]
        lines += ["", f"### Karışıklık tablosu — {'yalnızca görüntü' if m == 'image' else 'görüntü + veri'}", "",
                  "| Gerçek \\ Model | yükselen | düşen | yatay |", "|---|---|---|---|"]
        for t in TRENDS:
            cnt = {p: sum(1 for r in rs if r["trend"] == t and r["out"]["trend"] == p) for p in TRENDS}
            lines.append(f"| {TREND_TR[t]} | {cnt['up']} | {cnt['down']} | {cnt['flat']} |")
    models = sorted({r.get("model") or r["provider"] for r in rows})
    lines += ["", f"Kullanılan model(ler): {', '.join(models)}"]
    return "\n".join(lines) + "\n"


async def main_async(args) -> None:
    out_dir = Path(args.out)
    log_path = out_dir / "sonuc.jsonl"
    samples = [make_series(i) for i in range(args.n)]
    modes = ["image", "data"] if args.mode == "both" else [args.mode]
    done = load_done(log_path)

    if not args.report:
        provider = get_provider(args.provider)
        todo = [(s, m) for s in samples for m in modes if (s["id"], m) not in done]
        if args.limit:
            todo = todo[: args.limit]
        print(f"{len(done)} hazır, {len(todo)} istek yapılacak ({provider.name})")
        out_dir.mkdir(parents=True, exist_ok=True)
        for k, (s, m) in enumerate(todo, 1):
            img = render_png(s, out_dir / "img" / f"{s['id']}.png")
            row = await run_one(provider, s, m, img)
            with log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            mark = "HATA " + row["error"] if "error" in row else ("✓" if row["trend_ok"] else "✗") + f" {row['out']['trend']}"
            print(f"[{k}/{len(todo)}] {s['id']} {m:5} gerçek={s['trend']:4} → {mark} ({row['seconds']} sn)")
            if "error" in row and ("429" in row["error"] or "kota" in row["error"].lower()):
                print("Kota dolmuş görünüyor; yarın aynı komutla kaldığı yerden devam edin.")
                break
            if args.delay and provider.name != "fake":
                await asyncio.sleep(args.delay)
        done = load_done(log_path)

    rows = [r for r in done.values() if r["id"] in {s["id"] for s in samples} and r["mode"] in modes]
    (out_dir / "rapor.md").parent.mkdir(parents=True, exist_ok=True)
    (out_dir / "rapor.md").write_text(report(rows, args.n), encoding="utf-8")
    print(f"Rapor: {out_dir / 'rapor.md'} ({len(rows)} sonuç)")


def main() -> None:
    load_env()
    ap = argparse.ArgumentParser(description="Grafik okuma değerlendirmesi")
    ap.add_argument("--n", type=int, default=50, help="örnek grafik sayısı")
    ap.add_argument("--mode", choices=["image", "data", "both"], default="both")
    ap.add_argument("--provider", default=None, help="vars.: LLM_PROVIDER")
    ap.add_argument("--delay", type=float, default=8.0, help="istekler arası bekleme (sn)")
    ap.add_argument("--limit", type=int, default=0, help="bu çalıştırmada en fazla kaç istek")
    ap.add_argument("--out", default="grafik_eval")
    ap.add_argument("--report", action="store_true", help="istek atmadan yalnızca rapor üret")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
