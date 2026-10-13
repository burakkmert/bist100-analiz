# engine/ — Karar motoru (Kişi 2)

Kişi 1'in gece tahminlerini (forecasts) ve hata metriklerini (model_errors) yorumlayıp
`analysis` tablosunun satırlarını üretir. Saf hesap modülleri; veritabanı bağlantısı `run_engine.py`'de.

| Dosya | Görev |
|---|---|
| `indicators.py` | RSI, MACD, MA20/50 + kesişim, ATR, volatilite, hacim (fonlarda MACD/hacim yok) |
| `ensemble.py` | Ağırlık ∝ 1/MAE (son 60 gün, varlık × ufuk), alt sınır 0,1; kantil ortalaması |
| `regime.py` | trend / range / high_vol — hissede ADX, fonda Kaufman verimlilik oranı |
| `decision.py` | Yön (ATR eşiği), güven skoru 0–100 (bileşenleriyle), risk → analysis satırı |
| `config.yaml` | Tüm eşikler; Kişi 1'in backtest'iyle ayarlanacak |

Güven skoru = temel 30 + sinyal gücü (0–40) + model uyumu (0–30) − cezalar
(gösterge çelişkisi, düşük likidite, kısa geçmiş, yüksek oynaklık). Her bileşen
`analysis.indicators.confidence_parts` alanına yazılır; "neden bu sinyal?" ekranı (Aşama 2) buna dayanır.

Testler: `cd backend && pytest ../engine/tests -q` (veri sızıntısı testi dahil).
