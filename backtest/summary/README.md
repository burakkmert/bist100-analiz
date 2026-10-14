# Backtest özeti

Poster ve raporda kullanılacak **sonuç tabloları**. `backtest/reports/` (ham çıktılar) depoya girmez; buradaki dosyalar küçük ve elle derlenmiş özetlerdir. Ayrıntılı yorum: proje dokümanı `backtest_bulgulari_2026-10-10.md`.

## Kurulum
2026-10-12 koşusu: 478 BIST hissesi + 295 TEFAS fonu, son 504 işlem günü, ortak takvimden haftalık tahmin günleri, ufuklar 1/5/20/30/120 gün, bağlam 512 gün, sıfır atış (fine-tuning yok). Model tahmin gününden sonrasını görmez. Modeller: TimesFM 2.5, Chronos-2, naive (yarın = bugün), naive_drift (son 250 günün ortalama getirisi, yıllık ±%100 sınırlı).

## Ana bulgu
Sıfır atış TimesFM ve Chronos, doğru kurulmuş basit kıyası (hisselerde naive, fonlarda naive_drift) **istatistiksel olarak anlamlı biçimde geçemiyor**; bu fon kategorilerine bölünce de değişmiyor. Modellerin tek başına %80 aralıkları uzun ufukta fazla dar; uygulamadaki senaryo bandı (modeller + naive_drift) hedef kapsamaya (~0,80) yaklaşıyor.

## Dosyalar
| Dosya | İçerik |
| --- | --- |
| `hisse_478.csv` | Hisse: MASE, Diebold–Mariano oranı ve p, yön doğruluğu, %80 aralık kapsaması (ufuk başına) |
| `fon_295.csv` | Fon: MASE ve Diebold–Mariano (naive_drift'e karşı) |
| `fon_kategori_dm.csv` | Fon kategorisine göre DM oranı ve p (TimesFM, Chronos; 5/30/120 gün) |
| `senaryo_kapsama.csv` | Senaryo bandının kapsaması ve genişliği (% son fiyat) |
| `model_errors_mape.csv` | Son 60 işlem gününde medyan MAPE (%), model × ufuk, hisse ve fon |

## Nasıl okunur
- **MASE** < 1: naive'den iyi, > 1: kötü (yüzde hata üzerinden).
- **DM oranı** < 1 ve p < 0,05: model kıyastan anlamlı biçimde iyi; > 1 ve p küçük: anlamlı biçimde kötü.
- **Kapsama**: %80 aralığın gerçek değeri içine alma oranı; ideal ≈ 0,80.
- `<0.001`: p-değeri sıfıra yakın.
- Fon MASE'leri küçüktür (0,46–1,07) çünkü fon fiyatları düzgün ve trendli; hisse MASE'leri ~1'dir (rastgele yürüyüş).
