# Gece işleri: işletim notu (Kişi 2)

Her hafta içi akşam zincir şu sırayla çalışır (Türkiye saati):

| Saat  | Adım       | Komut                                   | job_runs satırını yazan |
|-------|------------|-----------------------------------------|-------------------------|
| 19:00 | collect    | `python -m data.run_daily --db`         | zamanlayıcı             |
| 20:00 | forecast   | `python -m ml.nightly --db`             | zamanlayıcı             |
| 21:30 | engine     | `python -m engine.run_engine`           | kendisi                 |
| 21:30 | signals    | `python -m engine.run_signals`          | kendisi                 |
| 22:00 | explain    | Kişi 3 (veritabanı modu gelince açılır) | zamanlayıcı             |
| 22:15 | push       | `python -m app.jobs.push`               | kendisi                 |
| 08:05 | push (her gün) | sessiz saatte bekleyenler + Expo receipt kontrolü | kendisi       |

Adımlar ve saatler `backend/app/jobs/nightly.yaml` dosyasında tanımlıdır.

## Çalıştırma

Zamanlayıcı, modellerin kurulu olduğu makinede çalışır (GPU'lu makine, Kişi 1'in ortamı). `DATABASE_URL` tanımlı olmalıdır.

```
cd backend
python -m app.jobs.nightly --serve                                # sürekli
python -m app.jobs.nightly --once --no-wait --date 2026-10-13     # bir geceyi hemen dene
python -m app.jobs.push --dry-run                                 # bildirim planını gör, gönderme
```

## Kurallar

- Önceki zorunlu adım başarısız olursa sonraki adımlar atlanır. Atlanan her adım için job_runs'a `failed` ve "atlandı: önceki adım (X) başarısız" yazılır.
- O gün başarıyla bitmiş bir adım tekrar çalışmaz. Sorun giderildikten sonra `--once` ile zinciri yeniden başlatmak yeterlidir; zincir kaldığı yerden devam eder.
- Zincir hafta sonu ve tam gün tatillerde çalışmaz. Tatil listesi `nightly.yaml` dosyasındadır ve her yıl Borsa İstanbul takvimiyle güncellenmelidir.

## Bildirimler

- Bir sinyal en fazla bir kez bildirilir. Gönderilen sinyal id'leri `job_runs('push').stats.sent_signal_ids` alanında tutulur.
- Sessiz saatte olan kullanıcının bildirimi 08:05'te gönderilir. 14 saatten eski bir sinyal artık bildirilmez.
- Kullanıcı başına gecelik bildirim sayısı `daily_push_limit` ile sınırlıdır (boşsa 5). Önce satış yönlü sinyaller, sonra güveni yüksek olanlar gider.
- Expo "DeviceNotRegistered" dönerse ilgili token silinir.
- Bildirim metni örneği: "THYAO · 5 günlük ufukta yükseliş yönlü model sinyali · güven 72 — Yatırım tavsiyesi değildir." Metinde "al/sat" geçmez (SPK).
