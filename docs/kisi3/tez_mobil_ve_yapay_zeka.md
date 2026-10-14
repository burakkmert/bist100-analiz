# Tez taslağı — Mobil uygulama ve yapay zekâ katmanı (Kişi 3)

> Durum: ilk taslak (Hafta 2). Köşeli parantez içindeki **[SONUÇ: …]** yerleri ölçümler tamamlanınca doldurulacak.
> Bu bölüm tezin "Uygulama" kısmına girer; ortak "Sonuç ve gelecek çalışmalar" bölümünü Kişi 3 birleştirir.

---

## 1. Giriş ve amaç

Bu bölüm, Borsa İstanbul hisseleri ve TEFAS fonları için geliştirilen tahmin sisteminin kullanıcıya ulaştığı
katmanı anlatır: mobil uygulama ve uygulamaya gömülü yapay zekâ asistanı. Amaç, model çıktılarını (olasılık
aralıkları, güven skorları, sinyaller) finans uzmanı olmayan bir kullanıcının anlayabileceği biçimde sunmak ve
kullanıcının "bu grafik ne anlatıyor?", "RSI nedir?" gibi sorularına uygulamanın kendi verisiyle tutarlı,
yatırım tavsiyesi içermeyen cevaplar vermektir.

Tasarımın üç temel ilkesi:

1. **Belirsizliği saklamamak.** Tek bir "hedef fiyat" yerine %80 olasılık aralığı (p10–p90) ve güven skoru gösterilir.
2. **Tavsiye vermemek.** Arayüz ve yapay zekâ emir kipi kullanmaz ("al/sat" yerine "alım yönlü model sinyali").
3. **Uydurmamak.** Yapay zekâ yalnızca sistemdeki sayıları kullanır; doğrulanamayan çıktı kullanıcıya gösterilmez.

## 2. Sistem mimarisindeki yeri

Mobil uygulama yalnızca backend (FastAPI) ile konuşur. Mobil ile backend arasındaki tüm uçlar ortak bir sözleşmede
(`shared/openapi.yaml`, v0.2: 19 uç, 20 şema) tanımlıdır. Bu sözleşme sayesinde mobil uygulama, backend henüz hazır
değilken aynı şekilde veri üreten sahte veri katmanıyla geliştirilmiş, gerçek uçlar hazır olunca tek bir ayarla
gerçek veriye geçilmiştir.

Yapay zekâ katmanı backend içinde ayrı bir modüldür (`backend/app/ai`). Dil modeline erişim anahtarı yalnızca
sunucuda tutulur; mobil uygulama paketinde hiçbir anahtar bulunmaz.

*Şekil önerisi: Sistem mimarisi (sunum PDF'indeki diyagram).*

## 3. Mobil uygulama

### 3.1 Teknoloji seçimi

| Bileşen | Seçim | Gerekçe |
|---|---|---|
| Çatı | Expo (SDK 57) + React Native | Tek kod tabanıyla iOS ve Android; Expo Go ile cihazda hızlı deneme |
| Dil | TypeScript (strict) | API şemasıyla birebir tipler; hatalar derleme anında (CI'da `tsc`) yakalanır |
| Gezinme | Expo Router | Dosya tabanlı yönlendirme; giriş/ilk kurulum durumuna göre korumalı ekran grupları |
| Sunucu verisi | TanStack Query | Önbellek, yükleniyor/hata durumları, yeniden deneme |
| Yerel durum | Zustand + AsyncStorage | Tema, risk profili, portföy, bildirim tercihleri cihazda kalıcı |
| Grafikler | react-native-svg (elle çizim) | Tahmin konisi, mum grafik ve parmakla gezinme için tam denetim |
| Animasyon | Reanimated 4 | UI iş parçacığında akıcı animasyon; klavye ile senkron yerleşim |

Hazır grafik kütüphaneleri (victory-native, wagmi-charts) değerlendirilmiş; tahmin konisinin son kapanıştan itibaren
genişleyen bir alan olarak çizilmesi ve mum/çizgi geçişi için elle çizim tercih edilmiştir.

### 3.2 Ekranlar ve akışlar

- **Giriş ve ilk kurulum:** yasal uyarı onayı (metin sürümü değişirse yeniden sorulur) ve 3 soruluk risk profili anketi.
- **Ana sayfa:** BIST 100 kartı, en güçlü model sinyalleri.
- **Piyasalar:** hisse/fon sekmeleri, arama, yön ve en düşük güven filtresi.
- **Varlık detayı:** fiyat grafiği (1A–5Y), 1/5/20 günlük tahmin bandı, 30/120 günlük senaryolar, güven skoru, risk ve
  rejim rozetleri, göstergeler, gece üretilen uzman yorumu, "Yorumla" ve "Aldım".
- **Sinyal detayı:** sinyalin yönü, ufku, stop seviyesi ve "Neden bu sinyal?" (modelin analizi, göstergeler, model ağırlıkları).
- **Portföy defteri:** "Aldım/Sattım" kayıtları, pozisyon başına ve toplam kâr/zarar.
- **Asistan ve grafik okuma:** bkz. Bölüm 4.
- **Bildirimler:** izin, sessiz saatler, günlük sınır; bildirime dokununca ilgili sinyal ekranı açılır.

Her tahmin ve sinyal ekranında kısa yasal uyarı şeridi görünür.

### 3.3 Arayüz tasarımı

Koyu temada laciverten koyu griye, açık temada pastel çok renkli bir zemin kullanılmıştır. Zemin, video yerine kodla
üretilen bir animasyondur: beş renkli ışık lekesi tek bir zamanlayıcıdan hesaplanan sinüs/kosinüs yörüngelerinde
dolaşır. Yalnızca konum ve ölçek değiştiği için animasyon GPU'da ucuzdur ve uygulama arka plandayken durur (pil).
Kartlar yarı saydam "cam" yüzeylerdir; açık temada okunurluk için ikincil metin kontrastı artırılmıştır.

### 3.4 Erişilebilirlik ve yerelleştirme

Tüm etkileşimli öğelerde ekran okuyucu etiketleri; Türkçe sayı biçimi (298,20 ₺); fonlarda TEFAS'taki gibi 4 ondalık;
Türkçe büyük/küçük harf dönüşümünde (I/ı, İ/i) özel işlem.

## 4. Yapay zekâ katmanı

### 4.1 Sağlayıcıdan bağımsız mimari

Tüm dil modeli çağrıları tek bir arayüzden geçer:

```python
class LLMProvider(Protocol):
    async def complete(self, system, messages, images=None) -> str: ...
    async def stream(self, system, messages) -> AsyncIterator[str]: ...
```

Gemini, DeepSeek, yerel Ollama ve testler için sahte bir sağlayıcı aynı arayüzü uygular; seçim `.env` dosyasındaki
`LLM_PROVIDER` ile yapılır. Böylece testler internetsiz ve ücretsiz çalışır, model değişikliği kod değişikliği gerektirmez.

### 4.2 Model seçimi

Ölçütler: görsel girdi desteği (grafik okuma için zorunlu), Türkçe kalitesi, maliyet, hız. Ücretsiz katman nedeniyle
Google Gemini ailesi seçilmiştir. Ücretsiz katmandaki model başına günlük istek sınırı (20) için birden çok modelden
oluşan bir **yedek zinciri** kurulmuştur: bir model kota, yoğunluk ya da zaman aşımı hatası verirse istek sıradaki
modele aktarılır; kotası dolan model saatlerce atlanır. Toplam bekleme 75 saniyeyle sınırlıdır.

Karşılaştırma 20 soruluk sabit bir test setiyle yapılmıştır (`app/ai/eval/compare.py`): terim açıklamaları, ekran
bağlamı soruları ve tavsiye almaya çalışan "kışkırtıcı" sorular.

| Model | Cevaplanan | Beklenen bilgi (cevaplananlarda) | Korkuluk ihlali | Ort. süre |
|---|---|---|---|---|
| Gemini 3.1 Flash-Lite | 17/20 | %94 | 1 (yanlış alarm, düzeltildi) | [SONUÇ] |

Seçim: Google Gemini (ücretsiz katman, yedek zinciriyle). Gerekçe: görsel girdi desteği (grafik okuma için zorunlu), Türkçe cevap kalitesi, ücretsiz kullanım ve tek bir API üzerinden birden çok model sürümüne geçebilme. Sağlayıcıdan bağımsız mimari sayesinde ileride başka bir modele geçiş yalnızca ayar değişikliği gerektirir.

### 4.3 Terim sözlüğü ve geri getirme (RAG)

162 Türkçe finans terimi (teknik göstergeler, model ve istatistik, temel analiz, fonlar, piyasa işlemleri, vergi) her biri
tanım, örnek ve "uygulamada nerede görülür" alanlarıyla yazılmıştır. Kullanıcının sorusuna en uygun tanımlar BM25
ile bulunur ve isteme eklenir; cevapta kaynak terimler gösterilir.

Plan aşamasında gömme (embedding) tabanlı arama düşünülmüştü. Sözlüğün küçük (162 kayıt) ve terim adlarının belirgin
olması nedeniyle BM25 hem yeterli doğruluk hem de sıfır ek maliyet (ayrı gömme modeli, vektör veritabanı yok) sağladığı
için tercih edilmiştir. [SONUÇ: istenirse BM25 ile gömme tabanlı aramanın küçük bir karşılaştırması]

### 4.4 Ekran bağlamı

Kullanıcı asistanı bir varlık ekranından açtığında, o varlığın analiz satırı (yön, güven, olasılık aralığı, risk, rejim,
göstergeler, model ağırlıkları) isteme düz Türkçe satırlar olarak eklenir. Veri veritabanından okunur
(`DbAnalysisSource`); veri yoksa model "veri yok" bilgisini alır ve sayı uydurmaması istenir.

### 4.5 Korkuluklar

- Sistem istemi: kendi fiyat tahmini üretmeme, al/sat dememe, verilen sayılarla çelişmeme, bilmediğini söyleme.
- Çıktı denetimi: emir kipi ve kesinlik ifadeleri ("alın", "kesin kazanç", "hedef fiyat") düzenli ifadelerle yakalanır;
  olumsuzluk içeren cümleler ("garanti getiri yoktur") istisna tutulur. İhlalli cevap güvenli bir metinle değiştirilir.

### 4.6 Akışlı sohbet

Cevap Server-Sent Events ile parça parça iletilir; kullanıcı ilk kelimeleri 1–2 saniyede görür. Akış sonunda kaynaklar
ve gerekirse korkuluk sonrası düzeltilmiş metin gönderilir.

### 4.7 Grafik okuma

Kullanıcı uygulamadaki grafiğin ("Yorumla") ya da galeri/kameradan bir grafiğin görüntüsünü gönderir. Model şu JSON
şemasında cevap verir: `trend`, `supports[]`, `resistances[]`, `pattern`, `indicators_note`, `summary`, `confidence_note`.
Çıktı şemaya zorlanır; bozuk alanlar güvenli varsayılanlarla değiştirilir.

Halüsinasyonu azaltmak için varlık kodu biliniyorsa son 120 işlem gününün sayısal özeti de isteme eklenir: başlangıç/son
fiyat ve yüzde değişim, en düşük/en yüksek, 20 ve 50 günlük ortalamalar, yerel dip/tepe kümelerinden hesaplanan
destek/direnç adayları ve son 10 kapanış. Kod bilinmiyorsa yorumun "yalnızca görsel desen yorumu" olduğu belirtilir.

**Değerlendirme** (`app/ai/eval/chart_eval.py`): doğru cevabı üretimden bilinen 50 sentetik grafik (yükselen, düşen,
bilinen bir bantta yatay). İki koşul: yalnızca görüntü / görüntü + 120 günlük veri.

| Koşul | Trend doğruluğu | Destek isabeti (±%3) | Direnç isabeti (±%3) | Makul seviye oranı |
|---|---|---|---|---|
| Yalnızca görüntü | [SONUÇ] | [SONUÇ] | [SONUÇ] | [SONUÇ] |
| Görüntü + veri | [SONUÇ] | [SONUÇ] | [SONUÇ] | [SONUÇ] |

[SONUÇ: sayısal verinin katkısı; karışıklık tablosundan çıkan hata türleri]

### 4.8 Gece uzman yorumları

Her gece analiz satırları için 2–3 cümlelik Türkçe yorum üretilir ve `ai_explanations` tablosuna yazılır. Maliyet için
yalnızca sinyali olan ya da en az bir kullanıcının izlediği varlıklar dil modeline gider; diğerlerine kurallı şablon
metin yazılır. Model metninde analizde bulunmayan bir sayı geçerse ya da korkuluk ihlali varsa yorum reddedilir ve
şablon kullanılır. [SONUÇ: bir gecelik çalışmada LLM / şablon / reddedilen oranları]

**Güven skorunun dili (kalibrasyon).** Kişi 1'in backtest kalibrasyonu (`backtest/summary/confidence_calibration.md`),
karar motorunun ham güven skorunun hisselerde isabeti ayırt etmediğini göstermiştir: 90–100 güvenli hisse sinyalleri de
yaklaşık %57 oranında tutmaktadır. Güven yalnızca fonlarda 5 ve 20 günlük yukarı yönlü sinyallerde anlamlıdır. Bu
nedenle yapay zekâ katmanı güveni bağlama göre dile getirir: anlamlı olmadığı durumlarda (tüm hisseler) metinler
"yüksek güven", "güçlü sinyal" gibi ifadeler kullanmaz, "yön sinyali zayıf, belirsizlik yüksek" der; bu kural hem
sistem istemlerinde hem de gece yorumlarının doğrulama adımında (bu ifadeleri içeren metin reddedilir) uygulanır.
Backend güveni "geçmişte benzer sinyallerin %X'i gerçekleşti" biçimine çevirdiğinde metinler bu oranı kullanır.

## 5. Yazılım kalitesi

- Ekip iş akışı: kişisel dallar, PR ve onay; ortak sözleşmelerde 3 onay.
- Otomatik kontroller (GitHub Actions): backend testleri, yapay zekâ katmanı testleri (51 test; veritabanı testleri
  CI'daki PostgreSQL'de çalışır), mobilde TypeScript tip denetimi.
- Güvenlik: anahtarlar yalnızca sunucudaki `.env`; repoya gönderimden önce gizli dosya denetimi.

## 6. Kullanıcı testi

[SONUÇ: 5–10 katılımcı, görevler, başarı oranları, SUS puanı, öne çıkan geri bildirimler — plan: `kullanici_testi_plani.md`]

## 7. Sınırlılıklar

- Model tarafındaki bulgu (Kişi 1, `backtest/summary/`): sıfır atış TimesFM/Chronos hisselerde naive'i, fonlarda
  naive_drift'i anlamlı biçimde geçememektedir (478 hisse, 295 fon). Senaryo bandı (modeller + naive_drift) hedef kapsamayı
  tutturmaktadır (fon 30 g 0,85 / 120 g 0,92; hisse 30 g 0,79 / 120 g 0,83); modellerin tek başına %80 aralıkları uzun
  ufukta fazla dar olduğu için uygulamada senaryo bandı gösterilir. Uygulamanın dili ("olasılık aralığı", "model görüşü",
  tavsiye yok) bu belirsizliğe uygun seçilmiştir.

- Ücretsiz katmandaki istek sınırı, aynı anda çok kullanıcıya hizmet vermeyi kısıtlar.
- Grafik okuma değerlendirmesi sentetik grafiklerle yapılmıştır; gerçek, gürültülü ekran görüntülerinde başarı daha düşük olabilir.
- iOS'ta uzak bildirim için ücretli Apple geliştirici hesabı gerekir; demo Expo Go ile yapılmıştır.

## 8. Gelecek çalışmalar

Sinyal sicili ekranı, "Neden bu sinyal?" için şelale grafiği, sanal portföy, KAP duyurularının dil modeliyle duygu
puanlaması (Aşama 2).
