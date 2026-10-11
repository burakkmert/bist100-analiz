# Fon Takip — Mobil (Kişi 3)

Expo + TypeScript + Expo Router. Bu klasör Kişi 3'ündür (`mobile/`).

## Hafta 1–2'de yapılanlar (Görev 1)

| Parça | Dosya |
|---|---|
| Hareketli arka plan (video yok, kodla) | `components/AnimatedBackground.tsx` |
| Tema: koyu = lacivert → koyu gri, açık = açık gri → beyaz | `theme/colors.ts`, `theme/ThemeProvider.tsx` |
| Liquid glass bileşenleri | `components/ui/` (GlassCard, GlassIcon, Button, TextField, Badge, Disclaimer) |
| Yüzen cam sekme çubuğu | `components/GlassTabBar.tsx` |
| Giriş / kayıt / şifre sıfırlama (Supabase, Google, Apple) | `app/(auth)/` |
| İlk açılış: yasal uyarı + 3 soruluk risk anketi → `PUT /me/profile` | `app/onboarding/` |
| Sekmeler: Ana sayfa, Piyasalar, Portföy, Ayarlar (mock veri) | `app/(tabs)/` |
| API istemcisi (token'ı `Authorization` başlığına ekler) | `api/client.ts` |

### Arka plan neden pil dostu?
- Animasyonlar Reanimated ile **UI iş parçacığında** döner; JS her karede çalışmaz.
- Yalnızca `transform` ve `opacity` değişir. Işık lekeleri SVG radyal gradyanla bir kez çizilir, sonra sadece kaydırılır — blur filtresi yok.
- Döngüler çok yavaş (18–37 sn).
- Uygulama arka plana geçince animasyon **durur**; cihazda "Hareketi azalt" açıksa hiç oynamaz.
- Android'de kartlarda canlı bulanıklık yok (hareketli zeminin üstünde her karede yeniden hesaplanır, pil yer). Yerine yarı saydam dolgu + ışık yansıması var. iOS'ta sistem bulanıklığı kullanılır.

## Kurulum

Gereken: Node.js 20+ ve telefonda **Expo Go**.

```bash
cd mobile
npm install
npx expo install --fix      # paket sürümlerini Expo SDK'ya hizalar
cp .env.example .env        # Windows: copy .env.example .env
npx expo start
```

Terminalde çıkan QR kodu Android'de Expo Go ile, iPhone'da Kamera uygulamasıyla okut.

> **Expo Go "SDK uyumsuz" derse:** Mağazadaki Expo Go yalnızca en güncel SDK'yı açar. O zaman:
> ```bash
> npx expo install expo@latest
> npx expo install --fix
> ```

Telefon ve bilgisayar aynı Wi-Fi'da olmalı. Okul ağı engelliyorsa: `npx expo start --tunnel`.

## Demo mod

`.env` içinde Supabase anahtarları boşsa giriş ekranında **"Demo modla devam et"** çıkar; tüm arayüz Supabase olmadan denenebilir. `EXPO_PUBLIC_MOCK=1` iken API yerine `mock/data.ts` kullanılır.

## Supabase bağlanınca (Kişi 2 projeyi açtıktan sonra)

1. `.env` → `EXPO_PUBLIC_SUPABASE_URL` ve `EXPO_PUBLIC_SUPABASE_ANON_KEY`.
2. Supabase → Authentication → URL Configuration → **Redirect URLs**'e ekle:
   - `fontakip://auth/callback` (development build ve yayın)
   - Expo Go için terminalde görünen `exp://192.168.x.x:8081/--/auth/callback`
3. Google ve Apple sağlayıcılarını Authentication → Providers'tan aç.

## Ne test edilmeli?

- [ ] Sistem temasını açık/koyu yap → arka plan gradyanı değişiyor mu?
- [ ] Ayarlar → Açık / Koyu / Sistem seçicisi anında çalışıyor mu?
- [ ] Arka plandaki ışık lekeleri yavaşça süzülüyor mu? Uygulamayı arka plana alıp dönünce devam ediyor mu?
- [ ] Yasal uyarı kutusu işaretlenmeden "Devam et" kapalı mı?
- [ ] Risk anketi sonunda profil (Temkinli/Dengeli/Atak) doğru çıkıyor mu?
- [ ] Uygulamayı kapatıp açınca anket tekrar sorulmuyor mu?
- [ ] Ana sayfada sinyal kartlarının altında uyarı metni var mı?

## Sıradaki adımlar (takvime göre)

- **Hafta 1–2 (kalan):** `shared/openapi.yaml`'ı ekiple yaz → `npx openapi-typescript ../shared/openapi.yaml -o api/schema.d.ts`.
- **Hafta 3–4:** Liste/detay ekranları Kişi 2'nin mock API'sine bağlanacak; mum/çizgi grafik, tahmin bandı, senaryo grafiği.
- **Hafta 5–6:** `backend/app/ai/` — LLMProvider, FakeProvider, terim sözlüğü, `/ai/chat`.
