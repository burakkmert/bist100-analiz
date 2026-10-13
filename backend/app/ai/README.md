# backend/app/ai — Yapay zekâ katmanı (Kişi 3)

| Dosya | Görev |
|---|---|
| `provider.py` | `LLMProvider` arayüzü, `FakeProvider`, `get_provider()` (`LLM_PROVIDER` ortam değişkeni) |
| `prompts/` | Türkçe sistem istemleri ve korkuluklar (sohbet, grafik okuma) |
| `guardrails.py` | İkinci savunma hattı: "hemen alın", "hedef fiyat 350" gibi cümleleri yakalar, uyarı satırını garanti eder |
| `glossary/*.md` | 162 terimlik Türkçe finans sözlüğü (tanım, örnek, uygulamada nerede) |
| `glossary.py` | Sözlük ayrıştırıcı |
| `rag.py` | Sözlük araması (BM25, bağımlılıksız). İleride gömme tabanlı arama aynı `Retriever` arayüzüyle eklenir |
| `context.py` | Ekran bağlamı → istem metni; `AnalysisSource` (Kişi 2'nin DB'si bağlanınca `DbAnalysisSource`) |
| `chat.py` | `/ai/chat` çekirdeği: RAG + bağlam + akış + korkuluk |
| `chart_read.py` | `/ai/chart-read` çekirdeği: görüntü + veri → şemaya zorlanmış JSON |
| `router.py` | FastAPI uçları |
| `explain_job.py` | Gece uzman yorumları (22:00): sinyalli/izlenen varlıklara LLM, diğerlerine şablon; uydurma sayı içeren yorumu reddeder |
| `eval/` | LLM sağlayıcı karşılaştırması (20 soru → tez tablosu) |
| `tests/` | 32 test |

## Kişi 2 için entegrasyon
```python
# backend/app/main.py
from app.ai.router import router as ai_router
app.include_router(ai_router)
```
- `requirements.txt`'teki paketleri backend bağımlılıklarına ekle.
- `router.py`, `app.core.auth.get_current_user`'ı import etmeye çalışır; yoksa geliştirmede anonim kullanıcıya izin verir.
- `get_analysis_source()` şimdilik `NullAnalysisSource` döner. DB oturumu hazır olunca `analysis` ve `prices`
  tablolarından okuyan bir `DbAnalysisSource` yazacağım (bu klasörde, `context.py` içinde).

## Testleri çalıştırma
```bash
cd backend
pip install -r app/ai/requirements.txt
pytest app/ai/tests -q
```

## Akış (SSE) biçimi — `POST /ai/chat` + `Accept: text/event-stream`
```
data: {"delta": "RSI "}
data: {"delta": "(Göreceli Güç Endeksi) ..."}
data: {"done": true, "sources": ["RSI (Göreceli Güç Endeksi)"]}
```
Korkuluk bir ihlal yakalarsa son olay `{"done": true, "replace": "<düzeltilmiş tam metin>"}` olur; istemci metni bununla değiştirir.
`Accept` başlığı event-stream değilse tek parça `{"reply": "..."}` döner.

## Sıradaki
- 6. hafta: 2–3 LLM adayıyla aynı 20 test sorusu → karşılaştırma tablosu → seçilen sağlayıcının adaptörü (`provider.register`).
- `DbAnalysisSource` (Kişi 2'nin DB'si hazır olunca).
- `explain_job.py` için DB kaynağı/hedefi (Kişi 2'nin gece işi orkestrasyonu çağıracak):
  `JsonSource`/`JsonSink` yerine analysis + signals + watchlist'ten okuyup ai_explanations'a yazan sürüm.
