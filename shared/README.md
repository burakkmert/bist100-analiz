# shared/ — Ortak sözleşmeler

Bu klasördeki dosyalar ekibin ortak sözleşmesidir. **Değişiklik yalnızca PR ile ve 3 onayla.**

| Dosya | Durum |
| --- | --- |
| `db_schema.sql` | Taslak v0.2 — ekip incelemesi bekliyor |
| `openapi.yaml` | Taslak v0.2.0 — ekip incelemesi bekliyor (Kişi 3; Kişi 2'nin kodundaki uçlarla hizalı) |

## Değişiklik geçmişi

| Sürüm | Değişiklik | Neden |
| --- | --- | --- |
| v0.2 | `assets.type` → `'index'` değeri eklendi | XU100 endeksi `prices` tablosuna yazılabilsin (`prices.code` → `assets.code` yabancı anahtarı). Kişi 2 rejim tespitinde endeksi kullanır. Endeks için tahmin, senaryo ve sinyal üretilmez. |
| v0.2 | `forecasts.model` yorumuna `naive_drift` eklendi | Backtest'te fonlarda en güçlü kıyas modeli; gece işi yazıyor. Yalnızca yorum, şema aynı. |
| v0.2 | `openapi.yaml` eklendi, `api_v0_eski.md` silindi | Mobil ile backend arasındaki tek sözleşme. `/stocks` → `/assets` (eski uçlar `deprecated`). Rejim değerleri `trend \| range \| high_vol`, sinyal ve pozisyon kimlikleri tam sayı (BIGSERIAL), `signals.outcome` → `{realized, hit}`. |
