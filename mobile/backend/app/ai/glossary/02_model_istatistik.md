# Model, tahmin ve istatistik

### Model sinyali
Eş: sinyal, model sinyali, sinyal neden geldi
Tanım: İstatistiksel modellerin belirli bir ufukta (1, 5 ya da 20 gün) fiyat yönü için ürettiği olasılıksal çıktı. Bir tavsiye değil, modelin görüşüdür.
Örnek: "THYAO, 5 günlük ufukta yükseliş yönlü model sinyali, güven 72" — modeller bu yönde büyük ölçüde uzlaşıyor demektir.
Uygulamada: Ana sayfadaki "Bugünün model sinyalleri" kartları.

### Güven skoru
Eş: güven, confidence, güven puanı
Tanım: 0–100 arası puan; modellerin bu yön konusunda ne kadar uzlaştığını ve geçmişte benzer durumlarda ne kadar tutarlı olduğunu özetler. Kesinlik anlamına gelmez.
Örnek: Güven 70, benzer geçmiş durumların çoğunda yönün doğru tahmin edildiğini anlatır; yine de yanılabilir.
Uygulamada: Sinyal kartlarındaki sayı ve detay ekranındaki güven çubuğu.

### Tahmin ufku
Eş: ufuk, horizon, vade
Tanım: Tahminin kaç işlem günü sonrası için yapıldığı. Uygulamada 1, 5 ve 20 günlük ufuklar vardır.
Örnek: 5 günlük ufuk, yaklaşık bir hafta sonrasının tahminidir.
Uygulamada: Detay ekranındaki "Tahmin ufku" seçici.

### Tahmin bandı
Eş: tahmin aralığı, tahmin konisi, mavi koni, olasılık aralığı, band
Tanım: Fiyatın belirli bir olasılıkla kalması beklenen aralık. Uygulamada alt sınır p10, üst sınır p90, ortadaki kesik çizgi p50'dir.
Örnek: "5 gün sonra %80 olasılıkla 366–431 aralığında" — bu, 10 senaryodan 8'inde fiyatın bu aralıkta kalması demektir.
Uygulamada: Detay ekranındaki grafikte "bugün"den sonra genişleyen mavi koni.

### Kantil
Eş: kantil, yüzdelik, quantile, persentil
Tanım: Bir dağılımı belirli oranlarda bölen değer. p10, sonuçların %10'unun bu değerin altında kalması beklenen noktadır.
Örnek: p90 = 120 ise fiyatın 120'yi aşma olasılığı yaklaşık %10'dur.
Uygulamada: Tahmin bandının sınırları (p10, p50, p90).

### p10 / p50 / p90
Eş: p10, p50, p90, alt sınır, orta değer, üst sınır
Tanım: Tahmin dağılımının %10, %50 ve %90 kantilleri. p50 ortanca (en olası orta) değerdir; p10–p90 arası %80'lik aralıktır.
Örnek: p10 = 95, p50 = 100, p90 = 106 ise model fiyatın büyük olasılıkla 95–106 arasında kalacağını düşünüyor.
Uygulamada: Model görüşü kartındaki "%80 olasılıkla … aralığında (orta değer …)" cümlesi.

### Güven aralığı
Eş: güven aralığı, confidence interval
Tanım: Bir tahminin belirsizliğini gösteren, gerçek değerin belirli bir olasılıkla içinde kalması beklenen aralık.
Örnek: %80 güven aralığı, aynı koşullar 10 kez tekrarlansa 8'inde sonucun aralıkta kalmasını bekler.
Uygulamada: Tahmin bandı bu fikirle çizilir.

### Senaryo analizi
Eş: senaryo, iyimser, temel, kötümser, bull, bear, base
Tanım: 30 ve 120 gün gibi uzun ufuklar için tek bir tahmin yerine iyimser, temel ve kötümser olası yolların gösterilmesi.
Örnek: 120 günde iyimser 650, temel 420, kötümser 270 — bunlar olası yollardır, gerçekleşecek fiyatın tahmini değildir.
Uygulamada: Detay ekranındaki "Senaryolar" grafiği.

### Ensemble (topluluk modeli)
Eş: ensemble, topluluk, birleşik model, model ağırlıkları
Tanım: Birden fazla modelin tahminlerini ağırlıklı olarak birleştirme yöntemi. Tek bir modelin hatalarını dengelemeye yarar.
Örnek: TimesFM %60, Chronos-2 %40 ağırlıkla birleştirilirse ensemble tahmini ikisinin ağırlıklı ortalamasıdır.
Uygulamada: Detay ekranındaki "Model ağırlıkları" çubuğu.

### TimesFM
Eş: timesfm, google timesfm
Tanım: Google'ın geliştirdiği, çok sayıda zaman serisiyle önceden eğitilmiş bir zaman serisi tahmin modeli.
Örnek: TimesFM bir hissenin geçmiş fiyatlarından gelecek günler için olasılık aralıkları üretir.
Uygulamada: Model ağırlıkları çubuğundaki modellerden biri.

### Chronos-2
Eş: chronos, chronos-2, amazon chronos
Tanım: Amazon'un geliştirdiği, önceden eğitilmiş zaman serisi tahmin modeli; ek değişkenleri (kovaryat) de kullanabilir.
Örnek: Chronos-2 aynı seriden TimesFM'den farklı bir aralık üretebilir; ikisi birleştirilir.
Uygulamada: Model ağırlıkları çubuğundaki modellerden biri.

### Rejim
Eş: piyasa rejimi, rejim, regime
Tanım: Piyasanın içinde bulunduğu genel durum: trend, yatay ya da oynak. Model ağırlıkları ve güven skoru rejime göre ayarlanabilir.
Örnek: Oynak rejimde tahmin aralıkları genişler ve güven skorları düşer.
Uygulamada: Detay ekranındaki rejim rozeti.

### Oynaklık (volatilite)
Eş: volatilite, oynaklık, dalgalanma
Tanım: Fiyatın ne kadar sert ve sık dalgalandığının ölçüsü. Genellikle getirilerin standart sapmasıyla hesaplanır.
Örnek: Yıllık volatilitesi %45 olan hisse, %20 olana göre çok daha geniş bir aralıkta hareket eder.
Uygulamada: Tahmin bandının genişliği ve risk rozeti buna bağlıdır.

### Risk rozeti
Eş: risk, düşük risk, orta risk, yüksek risk
Tanım: Varlığın son dönem oynaklığına göre düşük / orta / yüksek olarak sınıflandırılması.
Örnek: ATR %3,5 olan bir hisse "Yüksek risk" rozeti alır.
Uygulamada: Detay ekranındaki model görüşü kartı.

### Standart sapma
Eş: standart sapma, sigma
Tanım: Değerlerin ortalamadan ne kadar uzaklaştığının ölçüsü. Finansta oynaklığın temel hesaplama yoludur.
Örnek: Günlük getirilerin standart sapması %2 ise fiyat çoğu gün ±%2 civarında oynar.
Uygulamada: Oynaklık ve tahmin bandı hesaplarında.

### Getiri
Eş: getiri, kazanç oranı, return
Tanım: Bir yatırımın belirli bir sürede değerindeki yüzde değişim.
Örnek: 100 TL'ye alınıp 112 TL'ye satılan hissenin getirisi %12'dir.
Uygulamada: Değişim yüzdeleri ve portföy kâr/zararı.

### Logaritmik getiri
Eş: log getiri, logaritmik getiri
Tanım: Getirinin doğal logaritma ile hesaplanmış hâli; ardışık dönemlerin getirileri toplanabildiği için modellerde tercih edilir.
Örnek: %10 yükseliş yaklaşık 0,0953 log getiriye karşılık gelir.
Uygulamada: Modellerin iç hesaplarında.

### Backtest (geriye dönük test)
Eş: backtest, geriye dönük test, walk-forward
Tanım: Bir modelin ya da kuralın geçmiş veride "o gün bilinenlerle" nasıl performans göstereceğinin test edilmesi.
Örnek: Son iki yılın her haftası için yalnızca o tarihe kadarki veriyle tahmin yapılıp gerçekleşenle karşılaştırılır.
Uygulamada: Model performans raporları (/backtest/summary).

### MAE
Eş: mae, ortalama mutlak hata
Tanım: Tahminlerin gerçekleşen değerlerden ortalama ne kadar saptığının mutlak değeri.
Örnek: MAE 2,4 TL, tahminlerin ortalama 2,4 TL yanıldığını gösterir.
Uygulamada: Model performans tabloları.

### MAPE
Eş: mape, ortalama mutlak yüzde hata
Tanım: Tahmin hatasının gerçekleşen değere oranının ortalaması (yüzde).
Örnek: MAPE %3, tahminlerin ortalama %3 saptığını anlatır.
Uygulamada: Model performans tabloları.

### Yön doğruluğu
Eş: yön doğruluğu, isabet oranı, directional accuracy, hit rate
Tanım: Modelin fiyatın yükselip düşeceğini doğru bilme oranı.
Örnek: Yön doğruluğu %58 ise 100 tahminin 58'inde yön doğru çıkmıştır.
Uygulamada: Model performans tabloları ve ileride sinyal sicili ekranı.

### Baseline (temel karşılaştırma modeli)
Eş: baseline, naive, saf model
Tanım: Karmaşık modellerin karşılaştırıldığı basit tahmin yöntemi (ör. "yarın da bugünkü fiyat olur").
Örnek: Bir model baseline'ı geçemiyorsa ek bir değer üretmiyordur.
Uygulamada: Model performans tabloları.

### Aşırı öğrenme
Eş: overfitting, aşırı uyum, ezberleme
Tanım: Modelin geçmiş veriyi ezberleyip yeni veride başarısız olması.
Örnek: Backtestte çok iyi, gerçek hayatta kötü sonuç veren bir kural aşırı öğrenmiş olabilir.
Uygulamada: Model geliştirme sürecinde dikkat edilen konu.

### Kovaryat
Eş: kovaryat, ek değişken, covariate
Tanım: Tahmin edilen seriye ek olarak modele verilen yardımcı değişken (ör. endeks hareketi, haber duygusu).
Örnek: Chronos-2'ye BIST100 serisi kovaryat olarak verilebilir.
Uygulamada: Model tarafında; ileride KAP haber duygu puanı.

### Zaman serisi
Eş: zaman serisi, time series
Tanım: Zamana göre sıralı gözlemlerden oluşan veri (ör. günlük kapanış fiyatları).
Örnek: Bir hissenin son 5 yıllık günlük kapanışları bir zaman serisidir.
Uygulamada: Tüm fiyat grafikleri ve tahmin modelleri.

### Korelasyon
Eş: korelasyon, ilişki katsayısı
Tanım: İki değişkenin birlikte hareket etme derecesini -1 ile +1 arasında gösteren ölçü.
Örnek: İki banka hissesinin korelasyonu 0,85 ise genellikle aynı yönde hareket ederler.
Uygulamada: Uzman yorumlarında geçebilir.

### Beta
Eş: beta, piyasa duyarlılığı
Tanım: Bir hissenin piyasa endeksine göre ne kadar sert hareket ettiğinin ölçüsü. Beta 1'den büyükse endeksten daha oynaktır.
Örnek: Beta 1,4 olan hisse, endeks %1 yükseldiğinde ortalama %1,4 hareket eder.
Uygulamada: Uzman yorumlarında geçebilir.

### Olasılık
Eş: olasılık, ihtimal
Tanım: Bir olayın gerçekleşme şansının 0 ile 1 (ya da %0–%100) arasında ifadesi.
Örnek: %80 olasılıkla aralıkta kalması, %20 olasılıkla dışına çıkabileceği anlamına da gelir.
Uygulamada: Tahmin bandı açıklamaları.

### Halüsinasyon
Eş: halüsinasyon, uydurma, hallucination
Tanım: Yapay zekâ dil modelinin gerçekte olmayan bir bilgiyi kendinden emin biçimde üretmesi.
Örnek: Grafikte olmayan bir destek seviyesini "görmesi" bir halüsinasyondur; bu yüzden yorumlar sayısal veriyle karşılaştırılır.
Uygulamada: Asistan ve grafik okuma yorumlarının altındaki uyarı.
