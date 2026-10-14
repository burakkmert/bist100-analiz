# Güven skoru kalibrasyonu (2026-10-14)

`python -m backtest.confidence_calibration --raw backtest/reports/raw_2026-10-12_u500.parquet --every 2` çıktısı: Kişi 2'nin karar motoru (`engine.decision.analyze`) 773 varlık için geçmiş tahmin günlerinde yeniden çalıştırıldı (106.988 varlık-gün-ufuk). İsabet: up → fiyat yükseldi, down → düştü, flat → hareket motorun ATR eşiği içinde kaldı. Kıyas oranı: güvene bakmadan aynı (tür, ufuk, yön) için koşulsuz oran.

## Bulgu
- **Hisse:** güven skoru isabeti ayırt etmiyor (Spearman ≈ 0). 90–100 güvenli "flat" sinyaller %57 tutuyor; kıyas oranı da %57. Yön sinyali yok denecek kadar az (up/down toplam ~%1).
- **Fon, yukarı yön, 5 ve 20 gün:** güven arttıkça isabet artıyor (20g: 0,81 → 0,99; Spearman +0,18 / +0,22).
- **Fon, yukarı yön, 1 gün ve fon flat:** güven arttıkça isabet düşüyor (ters).
- Sebep (kod incelemesi): flat kararında model uyumu, "model bandı son fiyatı içeriyor mu" diye bakıyor; bant geniş olduğundan hep ~1 çıkıyor, skor yapısal olarak yüksek.

## Sınırlar
Yeniden oynatmada model ağırlıkları eşit (geçmiş model_errors arşivi yok; gerçek motor 1/MAE kullanır). Komşu tahmin günleri örtüştüğü için örnekler bağımsız değil: tablolar yönlendirici ölçümdür, anlamlılık testi değildir.

Dosyalar: `confidence_calibration.csv` (kovalara göre isabet), `confidence_spearman.csv` (güven ↔ isabet sıra korelasyonu).
