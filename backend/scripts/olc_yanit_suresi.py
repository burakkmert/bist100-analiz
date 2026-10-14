"""API yanıt sürelerini ölçer (tezdeki tablo için). Yalnızca standart kütüphane kullanır.

    python backend/scripts/olc_yanit_suresi.py https://fon-takip-api.onrender.com --token <JWT> --n 30

--token : uygulamada giriş yapmış bir kullanıcının Supabase erişim token'ı (mobilde
          supabase.auth.getSession() → access_token). Verilmezse yalnızca /health ölçülür.
Önce sunucu uyandırılır (Render ücretsiz katmanı uyuyorsa ilk istek ~1 dk); uyanma süresi ayrıca yazılır.
Her uç için n istek: ortalama, medyan, 95. yüzdelik (ms) ve sunucu içi süre (Server-Timing).
"""

from __future__ import annotations

import argparse
import statistics
import time
import urllib.error
import urllib.request

ENDPOINTS = [
    "/health",
    "/assets",
    "/assets?type=fund&q=a",
    "/assets/{code}/history?days=365",
    "/assets/{code}/forecast",
    "/assets/{code}/analysis?horizon=5",
    "/screener?direction=up",
    "/portfolio",
    "/signals?status=open",
    "/signals/track-record",
]


def fetch(url: str, token: str | None) -> tuple[int, float, float | None]:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"} if token else {})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            r.read()
            status, timing = r.status, r.headers.get("Server-Timing")
    except urllib.error.HTTPError as e:
        status, timing = e.code, e.headers.get("Server-Timing")
    total = (time.perf_counter() - t0) * 1000
    server = float(timing.split("dur=")[1]) if timing and "dur=" in timing else None
    return status, total, server


def p95(xs: list[float]) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, round(0.95 * (len(xs) - 1)))]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--token")
    ap.add_argument("--code", default="THYAO")
    ap.add_argument("--n", type=int, default=20)
    a = ap.parse_args()
    base = a.base.rstrip("/")

    _, wake, _ = fetch(base + "/health", None)
    print(f"Uyandırma (ilk istek): {wake:.0f} ms\n")
    print(f"{'Uç nokta':40} {'durum':>5} {'ort':>7} {'medyan':>7} {'p95':>7} {'sunucu':>7}")
    for ep in ENDPOINTS:
        if ep != "/health" and not a.token:
            continue
        url = base + ep.replace("{code}", a.code)
        res = [fetch(url, a.token) for _ in range(a.n)]
        totals = [r[1] for r in res]
        servers = [r[2] for r in res if r[2] is not None]
        srv = f"{statistics.median(servers):7.1f}" if servers else "      -"
        print(
            f"{ep:40} {res[-1][0]:>5} {statistics.mean(totals):7.0f} {statistics.median(totals):7.0f} "
            f"{p95(totals):7.0f} {srv}"
        )
    print("\nSüreler ms. 'sunucu' = Server-Timing (ağ hariç, medyan).")
    print("İlk /assets isteği 60 sn'lik önbelleği doldurur; sonrakiler önbellekten gelir.")


if __name__ == "__main__":
    main()
