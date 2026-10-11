"""POST /ai/chart-read çekirdeği: grafik görüntüsü (+ varsa sayısal veri) → yapılandırılmış yorum."""
from __future__ import annotations

import json
import re
from typing import Any

from . import guardrails
from .chat import decode_image, load_prompt
from .context import AnalysisSource, NullAnalysisSource, describe
from .provider import LLMProvider

VALID_TREND = {"up", "down", "flat"}
NO_DATA_NOTE = "Yalnızca görsel desen yorumu; sayısal veriyle karşılaştırılmadı."


def parse_chart_json(text: str) -> dict[str, Any]:
    """LLM çıktısını şemaya zorlar; bozuk ya da eksik alanlarda güvenli varsayılan kullanır."""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("Model JSON döndürmedi.")
    raw = json.loads(m.group(0))

    def nums(v: Any) -> list[float]:
        if not isinstance(v, list):
            return []
        out = []
        for x in v:
            try:
                out.append(round(float(str(x).replace(",", ".")), 4))
            except ValueError:
                continue
        return sorted(set(out))[:5]

    def s(v: Any) -> str | None:
        return str(v).strip() if isinstance(v, (str, int, float)) and str(v).strip() else None

    trend = raw.get("trend") if raw.get("trend") in VALID_TREND else "flat"
    summary = s(raw.get("summary")) or "Grafikten belirgin bir yorum çıkarılamadı."
    return {
        "trend": trend,
        "supports": nums(raw.get("supports")),
        "resistances": nums(raw.get("resistances")),
        "pattern": s(raw.get("pattern")),
        "indicators_note": s(raw.get("indicators_note")),
        "summary": guardrails.sanitize(summary).replace(f"\n\n{guardrails.DISCLAIMER}", ""),
        "confidence_note": s(raw.get("confidence_note")) or NO_DATA_NOTE,
    }


async def read_chart(
    image_data_uri: str,
    code: str | None,
    provider: LLMProvider,
    source: AnalysisSource | None = None,
) -> dict[str, Any]:
    image = decode_image(image_data_uri)
    if image is None:
        raise ValueError("Görsel gerekli.")
    if not provider.supports_images:
        raise ValueError("Seçili model görsel desteklemiyor.")
    src = source or NullAnalysisSource()

    context_lines = "Sayısal veri yok."
    has_data = False
    if code:
        code = code.upper()
        analysis = await src.get_analysis(code, 5)
        prices = await src.get_recent_prices(code, 120)
        parts = [describe({"screen": "asset_detail", "code": code}, analysis)]
        if prices:
            closes = [p.get("close") for p in prices if p.get("close") is not None]
            if closes:
                has_data = True
                parts.append(
                    f"Son {len(closes)} günün kapanışları (eskiden yeniye, özet): ilk {closes[0]}, son {closes[-1]}, "
                    f"en düşük {min(closes)}, en yüksek {max(closes)}"
                )
        context_lines = "\n".join(parts)

    system = f"{load_prompt('system_chart_read')}\n\n### EKRAN BAĞLAMI\n{context_lines}\n"
    text = await provider.complete(system, [{"role": "user", "content": "Bu grafiği yorumla."}], images=[image])
    result = parse_chart_json(text)
    if not has_data and "karşılaştırıl" not in result["confidence_note"]:
        result["confidence_note"] = NO_DATA_NOTE
    return result
