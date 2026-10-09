"""Model duman testi: TimesFM 2.5 ve Chronos-2'yi tek bir varlıkta çalıştırır.

Amaç: kurulum, GPU ve model indirmesi çalışıyor mu? Sonuçlar mantıklı mı?
İlk çalıştırmada modeller Hugging Face'ten iner (~1,5 GB), sonra önbellekten gelir.

Kullanım:
    python -m ml.smoke_test                 # THYAO, son 512 gün
    python -m ml.smoke_test --code IPB
    python -m ml.smoke_test --cpu           # GPU yerine CPU (süre karşılaştırması)
"""
from __future__ import annotations

import argparse
import time

import numpy as np
import pandas as pd

from data.collectors.bist_prices import read_cache

HORIZONS = [1, 5, 20, 30, 120]


def load_series(code: str, context: int) -> np.ndarray:
    df = read_cache(code)
    if df.empty:
        raise SystemExit(f"{code} önbellekte yok. Önce: python -m data.run_daily --stocks {code} --funds")
    price = df["adj_close"].fillna(df["close"]).astype("float32").to_numpy()
    return price[-context:]


def run_timesfm(series: np.ndarray, max_h: int, device: str) -> np.ndarray:
    """Dönüş: (max_h, 3) -> p10, p50, p90"""
    import timesfm
    import torch

    torch.set_float32_matmul_precision("high")
    model = timesfm.TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch")
    model.compile(timesfm.ForecastConfig(
        max_context=1024, max_horizon=128, normalize_inputs=True,
        use_continuous_quantile_head=True, force_flip_invariance=True,
        infer_is_positive=True, fix_quantile_crossing=True,
    ))
    _, quantiles = model.forecast(horizon=max_h, inputs=[series.copy()])
    # quantiles[0]: (h, 10) -> [ortalama, q10, q20, ..., q90]
    return quantiles[0][:, [1, 5, 9]]


def run_chronos(series: np.ndarray, max_h: int, device: str) -> np.ndarray:
    import torch
    from chronos import Chronos2Pipeline

    pipe = Chronos2Pipeline.from_pretrained("amazon/chronos-2", device_map=device, torch_dtype=torch.float32)
    quantiles, _ = pipe.predict_quantiles([series], prediction_length=max_h, quantile_levels=[0.1, 0.5, 0.9])
    # quantiles[0]: (1 değişken, h, 3)
    return quantiles[0][0].cpu().numpy()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--code", default="THYAO")
    p.add_argument("--context", type=int, default=512)
    p.add_argument("--cpu", action="store_true")
    args = p.parse_args()
    if args.cpu:  # GPU'yu torch yüklenmeden gizle; iki model de CPU'ya düşer
        import os
        os.environ["CUDA_VISIBLE_DEVICES"] = ""

    import torch
    device = "cuda" if torch.cuda.is_available() and not args.cpu else "cpu"
    series = load_series(args.code.upper(), args.context)
    last = float(series[-1])
    print(f"{args.code.upper()}: {len(series)} gün bağlam, son fiyat {last:.2f}, cihaz: {device}\n")

    rows = []
    for name, fn in [("timesfm", run_timesfm), ("chronos", run_chronos)]:
        t0 = time.time()
        try:
            q = fn(series, max(HORIZONS), device)
        except Exception as exc:
            print(f"[{name}] HATA: {exc}")
            continue
        print(f"[{name}] {time.time() - t0:.1f} sn (model yükleme dahil)")
        for h in HORIZONS:
            p10, p50, p90 = (float(x) for x in q[h - 1])
            rows.append({"model": name, "ufuk": h, "p10": p10, "p50": p50, "p90": p90,
                         "p50_degisim_%": (p50 / last - 1) * 100,
                         "aralik_genisligi_%": (p90 - p10) / last * 100})

    if rows:
        pd.set_option("display.float_format", "{:.2f}".format)
        print("\n" + pd.DataFrame(rows).to_string(index=False))
        print("\nKontrol: p10 < p50 < p90 olmalı; aralık genişliği ufuk büyüdükçe artmalı.")
        print("Not: 120 günlük p50 tezde/uygulamada nokta tahmin olarak KULLANILMAZ, yalnızca senaryo bandı.")


if __name__ == "__main__":
    main()
