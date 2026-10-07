# data/ — Kişi 1

| Dosya | Görev |
| --- | --- |
| `bist_stocks.csv` | BIST hisse listesi (code,name,sector) — tek doğru kaynak |
| `collectors/bist_list.py` | Listeyi okur/temizler; `--enrich` ile ad/sektörü yfinance'tan doldurur |
| `collectors/bist_prices.py` | yfinance OHLCV; 5 yıl ilk yükleme, sonra artımlı; önbellek + DB upsert |
| `config.yaml` | Fon evreni (ilk 300 + ek fonlar), geçmiş yıl sayısı |
| `collectors/tefas_list.py` | TEFAS fon listesi → büyüklüğe göre evren → `tefas_funds.csv` |
| `collectors/tefas_prices.py` | İlk yüklemede fon başına 5 yıl; sonra tek toplu çağrıyla eksik günler |

```bash
python -m data.collectors.bist_list --enrich
python -m data.collectors.bist_prices --codes THYAO GARAN --years 1   # hızlı deneme
python -m data.collectors.bist_prices --with-index                     # tüm liste + XU100
python -m data.collectors.tefas_list                                   # fon evreni (~2 istek)
python -m data.collectors.tefas_prices --codes IPB TTE                 # hızlı deneme
python -m data.collectors.tefas_prices                                 # tüm evren (ilk sefer ~40 dk)
pytest data/tests -q
```

Önbellek: `data/cache/prices/<KOD>.csv` (repoya girmez).
