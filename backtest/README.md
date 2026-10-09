# backtest/ — Kişi 1

Walk-forward test: model hiçbir zaman tahmin anından sonraki veriyi görmez.

| Dosya | Görev |
| --- | --- |
| `metrics.py` | MAE, MAPE, MASE (naive'e göre), yön doğruluğu + binom testi, kapsama, aralık genişliği |
| `walk_forward.py` | Yapılacak — son 2 yılda haftalık "o güne kadarki veriyle tahmin → gerçekleşenle karşılaştır" |
| `run_backtest.py` | Yapılacak — model × ufuk × varlık grubu tabloları → `reports/` |

**Okuma kılavuzu:** MASE < 1 → model naive'i geçiyor. Kapsama ≈ 0.80 → %80 aralık iyi kalibre.
Yön doğruluğu yalnızca binom p-değeri < 0.05 ise "yazı-turadan iyi" sayılır.

```bash
pytest backtest/tests -q
```
