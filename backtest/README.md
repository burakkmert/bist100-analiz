# backtest/ — Kişi 1

Walk-forward test: model hiçbir zaman tahmin anından sonraki veriyi görmez.

| Dosya | Görev |
| --- | --- |
| `metrics.py` | MAE, MAPE, MASE (naive'e göre), yön doğruluğu + binom testi, kapsama, aralık genişliği |
| `walk_forward.py` | Son 2 yılda (504 gün) haftalık tahmin günleri; model yalnızca o güne kadarki veriyi görür |
| `run_backtest.py` | Giriş noktası: walk-forward → model×ufuk ve hisse/fon×model×ufuk tabloları + `summary_<tarih>.json` |

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
