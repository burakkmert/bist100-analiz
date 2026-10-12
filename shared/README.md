# shared/ — Ortak sözleşmeler

Bu klasördeki dosyalar ekibin ortak sözleşmesidir. **Değişiklik yalnızca PR ile ve 3 onayla.**

| Dosya | Durum |
| --- | --- |
| `db_schema.sql` | Taslak v0.2 — ekip incelemesi bekliyor |
| `openapi.yaml` | Yapılacak (Kişi 2 + Kişi 3, Hafta 1–2) |
| `api_v0_eski.md` | v1 planından kalan eski API notu; `openapi.yaml` gelince silinecek |

## Değişiklik geçmişi

| Sürüm | Değişiklik | Neden |
| --- | --- | --- |
| v0.2 | `assets.type` → `'index'` değeri eklendi | XU100 endeksi `prices` tablosuna yazılabilsin (`prices.code` → `assets.code` yabancı anahtarı). Kişi 2 rejim tespitinde endeksi kullanır. Endeks için tahmin, senaryo ve sinyal üretilmez. |
| v0.2 | `forecasts.model` yorumuna `naive_drift` eklendi | Backtest'te fonlarda en güçlü kıyas modeli; gece işi yazıyor. Yalnızca yorum, şema aynı. |
