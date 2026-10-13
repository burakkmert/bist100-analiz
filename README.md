# Fon ve Hisse Takip Uygulaması

BIST hisseleri (~500+) ve TEFAS fonları için, hazır zaman serisi modelleri (Google TimesFM 2.5, Amazon Chronos-2) ile kendi karar motorumuzu birleştiren, grafik okuyup yorumlayan yapay zekâ destekli mobil uygulama. Bitirme projesi, 3 kişilik ekip.

> Bu uygulama yatırım tavsiyesi değildir (SPK). Metinler "model sinyali", "olasılık", "senaryo" diliyle yazılır.

## Mimari (gece işi, her iş günü)

| Saat | Adım | Sahibi |
| --- | --- | --- |
| 19:00 | Veri toplama + temizleme → `prices` | Kişi 1 |
| 20:00 | Tahmin → `forecasts`, `scenarios`, `model_errors` | Kişi 1 |
| 21:30 | Karar + sinyal motoru → `analysis`, `signals` | Kişi 2 |
| 22:00 | Uzman yorumu (LLM) → `ai_explanations` | Kişi 3 |
| 22:15 | Push bildirimleri | Kişi 2 |

Anlık istekler: Expo uygulaması ⇄ FastAPI ⇄ PostgreSQL; `/ai/*` → LLMProvider.

## Klasörler ve sahiplik

| Klasör | İçerik | Sahibi |
| --- | --- | --- |
| `data/` | BIST + TEFAS toplayıcılar, temizleme, doğrulama | Kişi 1 |
| `ml/` | TimesFM, Chronos-2, baseline'lar, gece tahmin işi | Kişi 1 |
| `backtest/` | Walk-forward testler, metrikler, raporlar | Kişi 1 |
| `engine/` | Göstergeler, ensemble, rejim, sinyal kuralları | Kişi 2 |
| `backend/app/{core,api,models,jobs}` | FastAPI, DB, auth, zamanlayıcı, push | Kişi 2 |
| `backend/app/ai/` | LLMProvider, grafik okuma, sohbet, RAG | Kişi 3 |
| `mobile/` | Expo (React Native, TypeScript) uygulaması | Kişi 3 |
| `shared/` | `db_schema.sql`, `openapi.yaml`, sabitler — **PR + 3 onay** | Ortak |
| `docs/` | Tez; her kişi kendi bölümü | Ortak |

## Kurulum (Python tarafı)

**Python 3.11 gerekli.** 3.9 ile kurulumda `curl_cffi` hatası alınır.

```bash
git clone https://github.com/burakkmert/bist100-analiz.git
cd bist100-analiz
py -3.11 -m venv .venv   # Mac/Linux: python3.11 -m venv .venv
# Windows: .venv\Scripts\activate   |   Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # değerleri doldur
```

## Backend'i çalıştırma (Docker)

Gerekenler: Docker Desktop (Windows'ta WSL 2 ile).

```bash
cp .env.example .env          # Windows: copy .env.example .env
docker compose up --build     # PostgreSQL 16 + FastAPI; şema göçleri otomatik uygulanır
```

- Swagger: http://localhost:8000/docs · sağlık: http://localhost:8000/health
- Veritabanı bilgisayardan `localhost:5432` (kullanıcı/şifre `fon`/`fon`, DB `fontakip`) olarak erişilebilir;
  Kişi 1'in `--db` seçenekli betikleri `.env`'deki `DATABASE_URL` ile doğrudan yazar.
- Kişi 3'ün LLM anahtarları `backend/.env` içinde durabilir; compose onu da okur.
- Mobilde Supabase girişi hazır olana kadar `.env`'de `AUTH_DEV_BYPASS=1` ile token'sız deneme yapılabilir.
- **Mock mod (`MOCK=1`, varsayılan):** `shared/openapi.yaml`'da olup henüz gerçek kodu yazılmamış uçlar
  sözleşmedeki örnek yanıtları döndürür (yanıt başlığında `X-Mock: 1`). Gerçek yazılmış uçlar (`/me/profile`,
  `/ai/*`) her zaman gerçektir; bir uç gerçek olarak yazıldıkça mock'tan kendiliğinden çıkar. Swagger'da
  "mock" etiketiyle görünür. Gerçek veriyle çalışmak için `MOCK=0`.

### Testler ve CI

Her PR'da GitHub Actions şunları çalıştırır: `ruff` (Kişi 2 kodu), `pytest backend/tests`,
`pytest backend/app/ai/tests`, mobil için `tsc`. Yerelde:

```bash
docker compose up -d db
cd backend && pip install -r requirements-dev.txt && pytest tests app/ai/tests -q
```

### Şema değişikliği

`shared/db_schema.sql` sözleşmedir; veritabanı Alembic göçleriyle kurulur (`backend/alembic/`).
`backend/tests/test_schema_contract.py` sözleşme ↔ göçler ↔ SQLAlchemy modellerinin aynı olduğunu
denetler. Değişiklik akışı: `db_schema.sql` + model + yeni göç (`alembic revision -m "..."`) → PR (3 onay).

## Git kuralları

- `main` korumalı, doğrudan push yok. PR + en az 1 onay + CI yeşil. `shared/` değişikliği 3 onay.
- Dal adı: `kisi1/feature/tefas-collector`, `kisi2/feature/signal-engine`, `kisi3/feature/chat-bubble`.
- Commit mesajı Türkçe ve açıklayıcı.
- `.env`, veri dosyaları ve model ağırlıkları repoya girmez.
