# Kişi 2 katkı listesi: Zahide Torun (GitHub: zahidetorun)

Rol: karar motoru ve backend (sistem mimarisi, veritabanı, API, karar ve sinyal motoru, bildirimler, gece işleri, yayına alma).

## Not: PR'ları açan hesap

Aşağıdaki "Açan hesap" sütununda **burakkmert** görünen PR'lar Kişi 2'nin işidir. Bu PR'lar, Kişi 2'nin kullandığı yapay zekâ asistanı oturumunun GitHub bağlantısı Kişi 1'in (Burak) hesabına bağlı olduğu için o hesapla açıldı; commit'lerde yazar olarak "Claude" görünür. İçerik, kod ve tez bölümü Kişi 2'ye aittir. Bu dosya Kişi 2'nin kendi hesabıyla eklenmiştir.

## Pull request'ler

| PR | Açan hesap | Konu | Plandaki görev |
|---|---|---|---|
| #17 | zahidetorun | Backend iskeleti: Docker, Alembic, Supabase JWT, `/me/profile`, CI | Görev 1 |
| #18 | zahidetorun | CI düzeltmesi, sözleşme v0.2 göçü, şema sözleşme testi | Görev 1 |
| #19 | zahidetorun | Göç düzeltmesi (şema SQL'i sürücüye doğrudan) | Görev 1 |
| #24 | zahidetorun | CI: veri, model ve backtest testleri | Görev 1 |
| #26 | zahidetorun | Mock mod | Görev 2 |
| #27 | zahidetorun | Teknik göstergeler ve veri sızıntısı testleri | Görev 3 |
| #28 | zahidetorun | Veri uçları: `/assets`, history, forecast, analysis, screener | Görev 4 |
| #29 | zahidetorun | Karar motoru: 1/MAE ensemble, rejim, yön, güven, risk | Görev 5 |
| #30 | zahidetorun | Gece karar motoru (`run_engine`) | Görev 5 |
| #33 | zahidetorun | Portföy, izleme listesi, push token, backtest özeti | Görev 6 |
| #34 | zahidetorun | Sinyal motoru, sinyal sicili, push bildirimleri, gece zinciri | Görev 7, 8, 9 |
| #35 | zahidetorun | Güven ve risk düzeltmesi (içeriği #38 ile birleşti) | Görev 5 |
| #37 | burakkmert | Geçici CI teşhisi (birleştirilmedi) | — |
| #38 | burakkmert | Güven kalibrasyonu motora bağlandı (+ #35'in içeriği) | Görev 5 |
| #40 | burakkmert | İstek sınırı (rate limit) | Görev 10 |
| #43 | burakkmert | Tez bölümü taslağı | Görev 10 |
| #44 | burakkmert | Yayına alma: Render + Supabase | Görev 10 |
| #46 | burakkmert | CI: mobil ESLint adımı | Görev 1 |
| #47 | burakkmert | Yanıt süresi ölçümü (Server-Timing + betik) | Görev 10 |
| #48 | burakkmert | Hata yönetimi ve sayfalama | Görev 4, 10 |
| #49 | burakkmert | Aşama 2: sinyal açıklaması ve sanal portföy | Aşama 2 |
| #50 | burakkmert | Tez: API yanıt süresi ölçümleri | Görev 10 |

## Kişi 2'nin sorumlu olduğu klasör ve dosyalar

- `engine/`: göstergeler, ensemble, rejim, karar motoru, kalibrasyon, sinyal motoru
- `backend/app/` (`backend/app/ai/` hariç; orası Kişi 3'ün): API, kimlik doğrulama, modeller, push, gece zinciri
- `backend/alembic/`, `backend/tests/`, `backend/Dockerfile`, `docker-compose.yml`, `render.yaml`, `.github/workflows/ci.yml`
- `docs/kisi2-*.md`: tez bölümü, gece işleri ve yayına alma rehberi
