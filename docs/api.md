# API sözleşmesi (v0.1)

Değişiklikler yalnızca PR ile ve üç kişinin onayıyla yapılır.

| Endpoint | Döndürdüğü | Durum |
| --- | --- | --- |
| `GET /stocks` | Sembol, ad, sektör, son fiyat, günlük değişim | sahte veri |
| `GET /stocks/{symbol}/history?days=365` | Geçmiş OHLCV | yapılacak |
| `GET /stocks/{symbol}/forecast` | 1/5/20 gün tahmin aralığı, model bazında ve ensemble | yapılacak |
| `GET /stocks/{symbol}/analysis` | Yön, güven, risk, rejim, yorum | sahte veri |
| `GET /screener?signal=up&min_conf=70` | Filtreye uyan hisseler | yapılacak |
| `GET /backtest/summary` | Model ve baseline metrikleri | yapılacak |

Örnek yanıt: `backend/mock/analysis_THYAO.json`
