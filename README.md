# BIST100 Analiz

BIST100 hisseleri için Google TimesFM ve Amazon Chronos modellerini kendi karar motorumuzla birleştiren, uzman gibi yorum yapan bir analiz uygulaması. Bitirme projesi.

> Bu uygulama yatırım tavsiyesi değildir.

## Mimari

```
Veri toplayıcı → Model servisi (TimesFM + Chronos) → Karar motoru
                                                        ↓
              PWA arayüz ← FastAPI backend ← Veritabanı
```

Tahminler her akşam seans kapanışından sonra toplu üretilir; uygulama hazır sonucu okur.

## Klasörler ve sorumlular

| Klasör | İçerik | Sorumlu |
| --- | --- | --- |
| `data/` | BIST100 listesi, fiyat verisi çekme ve temizleme | Kişi 2 |
| `models/` | TimesFM ve Chronos sarmalayıcıları, toplu tahmin | Kişi 1 |
| `engine/` | Ensemble, teknik göstergeler, rejim tespiti | Kişi 2 |
| `backtest/` | Walk-forward testler, baseline'lar, metrikler | Kişi 1 |
| `backend/` | FastAPI servisi | Kişi 2 |
| `frontend/` | PWA (web + mobil) | Kişi 3 |
| `docs/` | Tez, raporlar, API sözleşmesi | Kişi 3 |

## Kurulum

```bash
git clone https://github.com/burakkmert/bist100-analiz.git
cd bist100-analiz
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Fiyat verisini çek:

```bash
python data/fetch_prices.py --years 5
```

Backend'i sahte veriyle çalıştır:

```bash
uvicorn backend.app.main:app --reload
# http://127.0.0.1:8000/docs
```

## Çalışma kuralları

- `main` dalına doğrudan push yok. Her iş kendi dalında: `feature/chronos`, `feature/screener`.
- Birleştirme Pull Request ile, en az bir arkadaş onayıyla.
- Herkes kendi klasöründe çalışır; ortak dosyalar (`docs/api.md`, veritabanı modeli) yalnızca PR ile değişir.
- Veri dosyaları, model ağırlıkları ve `.env` repoya girmez (`.gitignore`).
