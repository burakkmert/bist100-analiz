# backtest/ — Kişi 1

Walk-forward test: model hiçbir zaman tahmin anından sonraki veriyi görmez.

| Dosya | Görev |
| --- | --- |
| `metrics.py` | MAE, MAPE, MASE (naive'e göre), yön doğruluğu + binom testi, kapsama, aralık genişliği |
| `walk_forward.py` | Son 2 yılda (504 gün) haftalık tahmin günleri; model yalnızca o güne kadarki veriyi görür |
| `run_backtest.py` | Giriş noktası: walk-forward → model×ufuk ve hisse/fon×model×ufuk tabloları + `summary_<tarih>.json` |
| `by_category.py` | Fon kategorisine göre kırılım: `python -m backtest.by_category --raw backtest\reports\raw_<tarih>_ctx512.parquet` → MASE, kapsama, naive_drift'e karşı DM (kategori TEFAS'tan, yoksa fon adından) |
| `confidence_calibration.py` | Güven skoru kalibrasyonu: Kişi 2'nin karar motorunu (`engine.decision.analyze`) geçmiş tahmin günlerinde yeniden çalıştırır; `python -m backtest.confidence_calibration --raw backtest\reports\raw_<tarih>.parquet` → güven aralığına göre gerçek isabet oranı, kıyas oranı, Spearman |
| `confidence_mapping.py` | Güven puanı → geçmiş isabet oranı eşlemesi (izotonik) + flat için tavan; zamana göre bölünüp ECE ile doğrulanır; çıktı `summary/confidence_mapping.json` (Kişi 2'nin motoru `display_confidence` / `capped_confidence` ile okur) |

**Okuma kılavuzu:** MASE < 1 → model naive'i geçiyor. Kapsama ≈ 0.80 → %80 aralık iyi kalibre.
Yön doğruluğu yalnızca binom p-değeri < 0.05 ise "yazı-turadan iyi" sayılır.

```bash
python -m backtest.run_backtest --codes THYAO GARAN IPB --models naive timesfm   # hızlı deneme
python -m backtest.run_backtest --models timesfm chronos naive ma               # tam evren
pytest backtest/tests -q
```

Not: ARIMA her bağlam için ayrı model kurduğundan tam evrende çok yavaştır (~36 bin fit);
ARIMA'yı ayrıca ve seyrek (`--step 20`) çalıştırmak önerilir.

## Görev 7 — bağlam uzunluğu deneyi
```powershell
powershell -ExecutionPolicy Bypass -File backtest\context_experiment.ps1   # 90/120/256/512, ~15 dk
python -m backtest.compare_contexts                                        # yalnızca karşılaştırma
```
Sonuç (2026-10-11): 512 gün varsayılan. Kısa bağlam hisselerde uzun ufukta naive_drift'e karşı
nokta hatayı düşürür ama düz naive'i geçmez ve kapsamayı bozar (hisse 120g: 0,60 vs 0,77).
