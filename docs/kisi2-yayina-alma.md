# Yayına alma: ücretsiz bulut (Kişi 2)

Ekip kararı: demo için ücretsiz bulut katmanı.

```
Mobil uygulama ──HTTPS──▶ Render (API sunucusu, ücretsiz) ──▶ Supabase Postgres (ücretsiz)
                                                                  ▲
Kişi 1'in makinesi (gece zinciri: veri → tahmin → motor → sinyal → bildirim) ──┘
```

| Parça | Nerede | Neden |
|---|---|---|
| Veritabanı | **Supabase** (giriş için zaten kullandığımız proje) | Ücretsiz, 500 MB, süresi dolmuyor. Render'ın ücretsiz Postgres'i 30 günde siliniyor. |
| API | **Render** ücretsiz web servisi (Docker) | Ücretsiz, Docker destekli, GitHub'dan kuruluyor |
| Gece işleri | Kişi 1'in makinesi | Modeller GPU istiyor, ücretsiz bulutta çalışmaz |

**Bilinmesi gereken sınırlar**

- **Render uykusu:** 15 dakika istek gelmezse sunucu uyur; ilk istekte uyanması yaklaşık 1 dakika sürer. Demodan birkaç dakika önce `https://<adres>/health` sayfasını açarak sunucuyu uyandırın. Aylık 750 saat ücretsiz kullanım tek servis için yeter.
- **Supabase boyutu:** Veritabanı en fazla 500 MB olabilir. Yüklemeden önce Kişi 1 kendi veritabanında boyutu ölçmeli: `SELECT pg_size_pretty(pg_database_size(current_database()));`. 400 MB'ı geçiyorsa önce bunu konuşalım; eski `forecasts` ve `analysis` satırlarını silen bir temizlik işi eklenebilir.
- **Supabase duraklatması:** Bir hafta hiç kullanılmayan ücretsiz proje duraklatılır; panelden "Restore" ile geri açılır. Gece işleri her gün yazdığı için normalde duraklamaz.

---

## 1. Veritabanı bağlantı metni (Supabase)

Bu adımı Supabase projesinin sahibi yapar.

1. Supabase panelinde projeyi aç.
2. **Project Settings → Database** bölümüne gir. Veritabanı şifresini bilmiyorsan **Reset database password** ile yeni bir şifre oluştur ve güvenli bir yere kaydet. **Şifreyi WhatsApp'a ya da sohbete yazma.**
3. Üstteki **Connect** düğmesine bas ve **Session pooler** satırındaki bağlantı metnini kopyala. Şuna benzer:
   `postgresql://postgres.<proje-kodu>:[YOUR-PASSWORD]@aws-0-<bölge>.pooler.supabase.com:5432/postgres`
4. `[YOUR-PASSWORD]` yerine şifreyi yaz. Şifrede `@ # / %` gibi özel karakterler varsa bunları URL kodlamasıyla yaz (`@` → `%40`, `#` → `%23`).

Neden **Session pooler**: Supabase'in doğrudan bağlantısı yalnızca IPv6 destekliyor, Render ise IPv4 kullanıyor. Pooler iki yönü de destekliyor.

Tablolar elle oluşturulmaz. API ilk açılışta `alembic upgrade head` çalıştırıp şemayı kendisi kurar. Bizim tablolar `public` şemasına yazılır; Supabase'in kendi `auth.users` tablosuyla çakışmaz.

## 2. API sunucusu (Render)

Repo herkese açık (public) olduğu için iki yol var.

**Yol A: Blueprint, otomatik güncellenir (önerilen).** Bunu repo sahibi Kişi 1 (burakkmert) yapmalı, çünkü Render'ın repoya bağlanma izni gerekiyor.

1. https://render.com adresinde **GitHub ile** kaydol.
2. **New → Blueprint** seç, `burakkmert/bist100-analiz` reposunu seç. Render kök dizindeki `render.yaml` dosyasını bulur.
3. Sorulan gizli değerleri gir:
   - `DATABASE_URL`: 1. adımda hazırladığın bağlantı metni.
   - `SUPABASE_URL`: `https://<proje-kodu>.supabase.co`
   - `EXPO_ACCESS_TOKEN`: boş bırakılabilir.
4. **Apply**'a bas. İlk kurulum 5–10 dakika sürer. Sonrasında main'e her birleştirmede sunucu kendiliğinden güncellenir.

**Yol B: Herkese açık repo URL'siyle (repo izni gerekmez, herkes yapabilir).**

1. Render'da **New → Web Service → Public Git Repository** seç ve `https://github.com/burakkmert/bist100-analiz` adresini gir.
2. Ayarlar:
   - Language: **Docker**
   - Branch: `main`
   - Dockerfile Path: `backend/Dockerfile`
   - Docker Build Context: `.`
   - Instance Type: **Free**
   - Region: **Frankfurt**
3. **Advanced → Health Check Path** alanına `/health` yaz.
4. **Environment** bölümüne şu değişkenleri ekle:
   - `APP_ENV=prod`
   - `MOCK=0`
   - `AUTH_DEV_BYPASS=0`
   - `CORS_ORIGINS=*`
   - `DATABASE_URL=...`
   - `SUPABASE_URL=...`
5. **Create Web Service**'e bas. Bu yolda güncellemeler kendiliğinden gelmez; main değişince panelde **Manual Deploy → Deploy latest commit**'e basılır.

**Kontrol:** Kurulum bitince `https://fon-takip-api.onrender.com/health` adresi (gerçek ad Render'da görünür) `{"status":"ok"}` göstermeli. `/docs` adresinde Swagger açılmalı.

## 3. Verinin yüklenmesi (Kişi 1)

Kişi 1, kendi `.env` dosyasında `DATABASE_URL`'i Supabase bağlantı metniyle değiştirip şunları sırayla çalıştırır:

```
python -m data.run_daily --db
python -m ml.nightly --db
python -m engine.run_engine
python -m engine.run_signals
```

Bundan sonra gece zinciri her akşam aynı veritabanına yazar:

```
cd backend
python -m app.jobs.nightly --serve
```

Bağlantı metni `postgresql://` ile başlasa da karar motoru ve backend bunu kendileri `postgresql+psycopg://` biçimine çevirir. Kişi 1'in veri ve model betikleri bunu yapmıyorsa, metnin başını elle `postgresql+psycopg://` olarak yazmak yeterli.

## 4. Mobil uygulama (Kişi 3)

API adresini Render'ın verdiği adresle değiştirmek yeterli: `https://<ad>.onrender.com`. Giriş zaten Supabase üzerinden yapılıyor; sunucu token'ı aynı projenin açık anahtarlarıyla (JWKS) doğrular.

## 5. Güvenlik kontrol listesi

- [ ] `DATABASE_URL` ve şifre yalnızca Render paneline ve Kişi 1'in `.env` dosyasına yazıldı. Depoya, sohbete ya da WhatsApp'a yazılmadı.
- [ ] `AUTH_DEV_BYPASS=0` ve `APP_ENV=prod` (geliştirme girişi kapalı).
- [ ] Supabase **service_role** anahtarı hiçbir yerde kullanılmıyor; sunucu ona ihtiyaç duymaz.
- [ ] Demodan sonra gerekirse Render servisi **Suspend** ile durdurulabilir.
