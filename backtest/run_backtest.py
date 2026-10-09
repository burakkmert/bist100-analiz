"""Backtest giriş noktası: walk-forward → metrik tabloları → backtest/reports/.

Kullanım:
    python -m backtest.run_backtest --codes THYAO GARAN IPB --models naive timesfm   # hızlı deneme
    python -m backtest.run_backtest --models timesfm chronos naive ma               # tam evren (ARIMA hariç)
    python -m backtest.run_backtest                                                 # tüm modeller (ARIMA yavaş!)
    python -m backtest.run_backtest --step 10 --test-days 252                       # daha kısa/seyrek

Çıktılar (backtest/reports/):
    raw_<tarih>.parquet                 her tahmin satırı (repoya girmez)
    by_model_horizon_<tarih>.csv        model × ufuk metrikleri
    by_type_model_horizon_<tarih>.csv   hisse/fon × model × ufuk metrikleri
    summary_<tarih>.json                /backtest/summary için özet (Kişi 2 sunar)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

from backtest.metrics import dm_table, summarize_by
from backtest.walk_forward import run_walk_forward
from ml.batch_forecast import load_price_frames, load_universe_codes
from ml.models.base import load_config
from ml.models.registry import build_models

REPORT_DIR = Path(__file__).resolve().parent / "reports"


def mase_pivot(table: pd.DataFrame) -> pd.DataFrame:
    """Okunaklı özet: satır model, sütun ufuk, değer MASE."""
    return table.pivot(index="model", columns="horizon", values="mase").round(3)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Walk-forward backtest")
    p.add_argument("--models", nargs="*", help="Boşsa config'teki tüm modeller")
    p.add_argument("--codes", nargs="*")
    p.add_argument("--limit", type=int)
    p.add_argument("--test-days", type=int, default=504, help="Son kaç işlem günü test edilir (~2 yıl)")
    p.add_argument("--step", type=int, default=5, help="Kaç günde bir tahmin günü (5 = haftalık)")
    p.add_argument("--context", type=int, help="Bağlam uzunluğu (varsayılan config)")
    p.add_argument("--append", action="store_true",
                   help="Bugünün raw dosyası varsa bu modellerin sonuçlarını ona ekle (diğer modeller korunur)")
    p.add_argument("--from-raw", help="Modelleri çalıştırma; kayıtlı raw_<tarih>.parquet'ten metrikleri yeniden hesapla")
    args = p.parse_args(argv)

    if args.from_raw:
        raw = pd.read_parquet(args.from_raw)
        report(raw, {"source": args.from_raw}, [], tag=Path(args.from_raw).stem.replace("raw_", ""), save_raw=False)
        return 0

    t0 = time.time()
    cfg = load_config()
    if args.context:
        cfg["context_length"] = args.context
    universe = load_universe_codes(args.codes)
    codes = universe["code"].tolist()[: args.limit] if args.limit else universe["code"].tolist()
    types = dict(zip(universe["code"], universe["type"]))
    frames, skipped = load_price_frames(codes, cfg.get("min_history", 120), types=types)
    if not frames:
        print("Veri yok. Önce: python -m data.run_daily", file=sys.stderr)
        return 1

    models = build_models(args.models, cfg)
    raw, stats = run_walk_forward(frames, models, cfg["horizons"], args.test_days, args.step,
                                  cfg.get("min_history", 120), cfg["context_length"])
    if raw.empty:
        print("Değerlendirme üretilemedi.", file=sys.stderr)
        return 1
    raw["type"] = raw["code"].map(types).fillna("unknown")
    tag = date.today().isoformat()
    old_path = REPORT_DIR / f"raw_{tag}.parquet"
    if args.append and old_path.exists():
        old = pd.read_parquet(old_path)
        old = old[~old["model"].isin(raw["model"].unique())]
        print(f"--append: önceki {old['model'].nunique()} modelin sonuçları korunuyor")
        raw = pd.concat([old, raw], ignore_index=True)
    settings = {"test_days": args.test_days, "step": args.step, "context_length": cfg["context_length"],
                "horizons": cfg["horizons"], "assets": len(frames), "skipped": len(skipped)}
    report(raw, settings, stats, tag=tag, started=t0)
    return 0


def report(raw: pd.DataFrame, settings: dict, stats: list, tag: str, save_raw: bool = True,
           started: float | None = None) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    if save_raw:
        raw.to_parquet(REPORT_DIR / f"raw_{tag}.parquet", index=False)
    by_mh = summarize_by(raw, ["model", "horizon"])
    by_tmh = summarize_by(raw, ["type", "model", "horizon"])
    by_mh.to_csv(REPORT_DIR / f"by_model_horizon_{tag}.csv", index=False)
    present = list(raw["model"].unique())
    focus = [m for m in ("timesfm", "chronos") if m in present]
    refs = [r for r in ("naive", "naive_drift") if r in present]
    step = int(settings.get("step", 5) or 5)
    dm = dm_table(raw, focus, refs, step=step, by=["type"])
    dm.to_csv(REPORT_DIR / f"diebold_mariano_{tag}.csv", index=False)
    by_tmh.to_csv(REPORT_DIR / f"by_type_model_horizon_{tag}.csv", index=False)

    summary = {
        "run_date": tag,
        "settings": settings,
        "models": stats,
        "by_model_horizon": by_mh.round(4).to_dict("records"),
        "duration_s": round(time.time() - started, 1) if started else None,
    }
    (REPORT_DIR / f"summary_{tag}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    pd.set_option("display.width", 200)
    print("\n== MASE (naive'e göre; < 1 ise naive'den iyi)")
    print(mase_pivot(by_mh).to_string())
    print("\n== Yön doğruluğu (p < 0.05 ise yazı-turadan anlamlı farklı)")
    print(by_mh.pivot(index="model", columns="horizon", values="dir_acc").round(3).to_string())
    print("\n== Kapsama (%80 aralık; ideal ≈ 0.80)")
    print(by_mh.pivot(index="model", columns="horizon", values="coverage").round(3).to_string())
    print("\n== Yön p-değerleri")
    print(by_mh.pivot(index="model", columns="horizon", values="dir_pvalue").round(3).to_string())
    for kind, g in by_tmh.groupby("type"):
        print(f"\n######## {kind.upper()} ({raw.loc[raw['type'] == kind, 'code'].nunique()} varlık)")
        for metric, title in [("mase", "MASE"), ("dir_acc", "Yön doğruluğu"),
                              ("dir_pvalue", "Yön p-değeri"), ("coverage", "Kapsama")]:
            print(f"-- {title}")
            print(g.pivot(index="model", columns="horizon", values=metric).round(3).to_string())
    if not dm.empty:
        print("\n######## DIEBOLD–MARIANO (rel_loss < 1 ve p < 0.05 -> kıyastan anlamlı derecede iyi)")
        for (kind, ref), g in dm.groupby(["type", "vs"]):
            print(f"-- {kind.upper()} | kıyas: {ref}")
            t = g.pivot(index="model", columns="horizon", values="rel_loss").round(3).astype(str) + " (p=" + \
                g.pivot(index="model", columns="horizon", values="p_value").round(3).astype(str) + ")"
            print(t.to_string())
    print(f"\nTablolar: {REPORT_DIR}  |  Süre: {summary['duration_s']} sn")


if __name__ == "__main__":
    sys.exit(main())
