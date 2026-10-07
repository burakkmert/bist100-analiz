# engine/ — Kişi 2

Karar motoru:
1. Dinamik ağırlıklı ensemble (ağırlık ∝ 1/MAE, son N gün)
2. Teknik sinyaller: RSI, MACD, 20/50 MA, ATR, hacim
3. Rejim tespiti: trend / yatay / yüksek volatilite
4. Çıktı: `docs/api.md` içindeki analysis formatı
