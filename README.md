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

```bash
git clone https://github.com/burakkmert/bist100-analiz.git
cd bist100-analiz
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # değerleri doldur
```

Docker Compose (PostgreSQL 16 + backend) ve CI Kişi 2 tarafından eklenecek.

## Git kuralları

- `main` korumalı, doğrudan push yok. PR + en az 1 onay + CI yeşil. `shared/` değişikliği 3 onay.
- Dal adı: `kisi1/feature/tefas-collector`, `kisi2/feature/signal-engine`, `kisi3/feature/chat-bubble`.
- Commit mesajı Türkçe ve açıklayıcı.
- `.env`, veri dosyaları ve model ağırlıkları repoya girmez.
