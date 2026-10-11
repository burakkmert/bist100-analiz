// Yasal metinler tek yerde durur. Metin değişirse DISCLAIMER_VERSION artırılır;
// kullanıcıdan uyarıyı yeniden onaylaması istenir.
export const DISCLAIMER_VERSION = 1;

export const DISCLAIMER_SHORT =
  'Model sinyalidir, yatırım tavsiyesi değildir. Kararlarınızın sorumluluğu size aittir.';

export const DISCLAIMER_FULL: { title: string; body: string }[] = [
  {
    title: 'Yatırım danışmanlığı değildir',
    body:
      'Bu uygulama, Sermaye Piyasası Kurulu (SPK) mevzuatı kapsamında yatırım danışmanlığı hizmeti vermez. ' +
      'Gösterilen tahminler, senaryolar ve sinyaller istatistiksel modellerin çıktısıdır; kişisel durumunuz dikkate alınmaz.',
  },
  {
    title: 'Model sinyali ve olasılık',
    body:
      'Tahminler geçmiş fiyat verisine dayanır ve olasılık aralığı olarak sunulur. Geçmiş performans gelecekteki sonuçların ' +
      'göstergesi değildir. Gerçekleşen fiyatlar aralığın dışına çıkabilir.',
  },
  {
    title: 'İşlemleri siz yaparsınız',
    body:
      'Uygulama hiçbir banka veya aracı kuruma bağlanmaz, sizin adınıza işlem yapmaz. "Aldım / sattım" kayıtları yalnızca ' +
      'kendi takibiniz içindir.',
  },
  {
    title: 'Yapay zekâ yorumları',
    body:
      'Grafik okuma ve sohbet özellikleri bir dil modeliyle çalışır. Model hata yapabilir; yorumları sayısal verilerle ' +
      'birlikte değerlendirin.',
  },
];
