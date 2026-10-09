"""Model duman testi: tüm modelleri (TimesFM, Chronos, naive, MA, ARIMA) aynı varlıkta
çalıştırıp yan yana gösterir. Sarmalayıcıların ve kurulumun çalıştığını doğrulamak içindir.

Kullanım:
    python -m ml.smoke_test                         # THYAO, tüm modeller
    python -m ml.smoke_test --code IPB
    python -m ml.smoke_test --models naive arima    # yalnızca bazı modeller
    python -m ml.smoke_test --cpu                   # GPU yerine CPU (süre karşılaştırması)
"""
from __future__ import annotations

import argparse
import os
import time

import pandas as pd

from data.collectors.bist_prices import read_cache


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--code", default="THYAO")
    p.add_argument("--models", nargs="*", default=["timesfm", "chronos", "naive", "moving_average", "arima"])
    p.add_argument("--cpu", action="store_true")
    args = p.parse_args()
    if args.cpu:  # GPU'yu torch yüklenmeden gizle
        os.environ["CUDA_VISIBLE_DEVICES"] = ""

    from ml.models.base import load_config
    from ml.models.registry import build_models

    cfg = load_config()
    code = args.code.upper()
    df = read_cache(code)
    if df.empty:
        raise SystemExit(f"{code} önbellekte yok. Önce veriyi çek: python -m data.run_daily --stocks {code} --funds")
    prices = df["adj_close"].fillna(df["close"]).to_numpy()
    last = float(prices[-1])
    print(f"{code}: {len(prices)} gün geçmiş, son fiyat {last:.2f}\n")

    frames = []
    for model in build_models(args.models, cfg):
        t0 = time.time()
        try:
            out = model.predict({code: prices}, cfg["horizons"])
        except Exception as exc:
            print(f"[{model.name}] HATA: {exc}")
            continue
        print(f"[{model.name}] {time.time() - t0:.1f} sn")
        frames.append(out.assign(model=model.name))

    if not frames:
        return
    res = pd.concat(frames, ignore_index=True)
    res["p50_degisim_%"] = (res["p50"] / last - 1) * 100
    res["aralik_%"] = (res["p90"] - res["p10"]) / last * 100
    res["p10_son_fiyat_ustu"] = res["p10"] > last  # True ise model aşağı ihtimali neredeyse görmüyor
    pd.set_option("display.float_format", "{:.2f}".format)
    print("\n" + res[["model", "horizon", "p10", "p50", "p90", "p50_degisim_%", "aralik_%",
                      "p10_son_fiyat_ustu"]].to_string(index=False))
    print("\nNot: 120 günlük p50 veritabanına yazılmaz; yalnızca senaryo bandı için kullanılır.")


if __name__ == "__main__":
    main()
