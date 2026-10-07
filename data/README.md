# data/ — Kişi 1

| Dosya | Görev |
| --- | --- |
| `bist_stocks.csv` | BIST hisse listesi (code,name,sector) — tek doğru kaynak |
| `collectors/bist_list.py` | Listeyi okur/temizler; `--enrich` ile ad/sektörü yfinance'tan doldurur |
| `collectors/bist_prices.py` | yfinance OHLCV; 5 yıl ilk yükleme, sonra artımlı; önbellek + DB upsert |
| `collectors/tefas_*.py` | Yapılacak |

```bash
python -m data.collectors.bist_list --enrich
python -m data.collectors.bist_prices --codes THYAO GARAN --years 1   # hızlı deneme
python -m data.collectors.bist_prices --with-index                     # tüm liste + XU100
pytest data/tests -q
```

Önbellek: `data/cache/prices/<KOD>.csv` (repoya girmez).
