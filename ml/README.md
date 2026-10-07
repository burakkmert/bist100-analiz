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
