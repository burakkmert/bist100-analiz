# models/ — Kişi 1

TimesFM ve Chronos sarmalayıcıları. Hedef arayüz, iki model için aynı:

```python
def predict(series: pd.Series, horizon: int, context: int = 120) -> pd.DataFrame:
    """Dönen sütunlar: q10, q50, q90 (horizon satır)."""
```

- Gemini ile yapılan test kodu buraya taşınıp arayüzden ayrılacak.
- Model ağırlıkları repoya girmez; Hugging Face önbelleğinden yüklenir.
