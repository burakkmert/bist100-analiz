# ml/ — Kişi 1

TimesFM 2.5 ve Chronos-2 sarmalayıcıları (sıfır atış), baseline'lar ve gece toplu tahmin işi (20:00).

Ortak arayüz (`ml/models/base.py`):

```python
class Forecaster:
    name: str
    def predict(self, series: dict[str, np.ndarray], horizons: list[int]) -> pd.DataFrame:
        """Dönüş sütunları: code, horizon, p10, p50, p90"""
```

Model ağırlıkları repoya girmez; Hugging Face önbelleğinden yüklenir.

## Dosyalar

| Dosya | Görev |
| --- | --- |
| `config.yaml` | Ufuklar, context uzunluğu, batch boyutları, cihaz |
| `models/base.py` | `Forecaster` arayüzü, seri temizleme, kantil sırası düzeltme |
| `models/baselines.py` | Naive, hareketli ortalama, ARIMA (kıyas modelleri) |
| `models/timesfm_model.py` | TimesFM 2.5 sarmalayıcı (batch, GPU) |
| `models/chronos_model.py` | Chronos-2 sarmalayıcı (batch, GPU) |
| `models/registry.py` | `build_models(["timesfm", ...])` — config'ten model oluşturur |
| `batch_forecast.py` | **Gece giriş noktası (20:00):** tüm evren × tüm modeller → `forecasts` biçimi (120 günde p50 = NULL), `--db` upsert |
| `model_errors.py` | **Gece (batch_forecast'tan sonra):** son 60 günde gerçekleşen tahminlerin varlık×model×ufuk hataları → `model_errors` (Kişi 2 ensemble ağırlıkları) |
| `smoke_test.py` | Tüm modelleri tek varlıkta yan yana çalıştırır |

```bash
python -m ml.smoke_test --code THYAO
python -m ml.batch_forecast --codes THYAO GARAN IPB   # hızlı deneme
python -m ml.batch_forecast                           # tam gece işi
python -m ml.model_errors                             # gece hata tablosu (~2-3 dk)
pytest ml/tests -q
```

Windows notu: TimesFM `torch_compile=False` ile yüklenir (torch.compile Triton ister).
