"""Mock mod (MOCK=1): sözleşmede (shared/openapi.yaml) olup henüz gerçek kodu yazılmamış
uç noktalar, sözleşmedeki örnek yanıtları döndürür. Kişi 3 backend'i beklemeden çalışabilsin diye.

Kurallar
- Gerçek kodu yazılmış uçlar (ör. /me/profile, /ai/*) daima gerçek koddan çalışır; mock onları ezmez.
  Yani bir uç noktayı gerçek olarak yazdıkça mock'tan kendiliğinden çıkar.
- Örnek seçimi:
    1) Yanıtın kendi örneği varsa o döner.
    2) Yoksa aynı şemayı kullanan başka bir uç noktanın örneği kullanılır
       (ör. /screener → /assets örneği; PATCH /portfolio/{id} → GET /portfolio'daki ilk pozisyon).
    3) POST/PUT/PATCH'te gönderilen gövde bu örneğin üzerine yazılır (istemci yazdığını geri görür).
    4) Hiçbiri yoksa boş nesne/liste döner; 204 yanıtlarında gövde yoktur.
- Yol parametresi {code} varsa yanıttaki "code" alanı istenen koda çevrilir.
- Liste yanıtlarında ?q= (kod/ad araması) ve alan adıyla eşleşen sorgu parametreleri (?type=fund,
  ?direction=up ...) süzgeç olarak uygulanır.
- Kimlik doğrulama istenmez; yanıtlarda "X-Mock: 1" başlığı bulunur.
"""

from __future__ import annotations

import copy
import json
import logging
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

log = logging.getLogger(__name__)

SPEC_PATH = Path(__file__).resolve().parents[3] / "shared" / "openapi.yaml"
METHODS = ("get", "post", "put", "patch", "delete")
# Kişi 3'ün gerçek router'ı ve eski iskelet uçları mock'a girmez
SKIP_PREFIXES = ("/ai/", "/stocks")
MOCK_HEADERS = {"X-Mock": "1"}


def load_spec(path: Path = SPEC_PATH) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- örnek seçimi


def _success(op: dict) -> tuple[int, dict]:
    """İlk 2xx yanıtın durum kodu ve tanımı."""
    for code, resp in (op.get("responses") or {}).items():
        if str(code).startswith("2"):
            return int(code), resp if isinstance(resp, dict) else {}
    return 200, {}


def _json(resp: dict) -> dict:
    return (resp.get("content") or {}).get("application/json") or {}


def _ref(schema: dict | None) -> str | None:
    return (schema or {}).get("$ref")


def _example_index(spec: dict) -> tuple[dict[str, Any], dict[str, list]]:
    """Şema adı → tekil örnek ve şema adı → liste örneği (tüm uçlardaki örneklerden)."""
    single: dict[str, Any] = {}
    many: dict[str, list] = {}
    for ops in spec.get("paths", {}).values():
        for method, op in ops.items():
            if method not in METHODS:
                continue
            for part in [_json(_success(op)[1]), _json(op.get("requestBody") or {})]:
                ex, schema = part.get("example"), part.get("schema") or {}
                if ex is None:
                    continue
                if _ref(schema) and isinstance(ex, dict):
                    single.setdefault(_ref(schema), ex)
                items = _ref(schema.get("items")) if schema.get("type") == "array" else None
                if items and isinstance(ex, list):
                    many.setdefault(items, ex)
                    if ex and isinstance(ex[0], dict):
                        single.setdefault(items, ex[0])
    return single, many


def pick_example(op: dict, spec: dict) -> tuple[int, Any]:
    """Bir işlem için (durum kodu, örnek gövde). Gövde yoksa None."""
    status, resp = _success(op)
    if status == 204:
        return status, None
    content = _json(resp)
    if "example" in content:
        return status, copy.deepcopy(content["example"])

    single, many = _example_index(spec)
    schema = content.get("schema") or {}
    if _ref(schema) in single:
        return status, copy.deepcopy(single[_ref(schema)])
    if schema.get("type") == "array":
        items = _ref(schema.get("items"))
        return status, copy.deepcopy(many.get(items, []))
    return status, {}


# --------------------------------------------------------------------------- yanıtı isteğe uydurma


def _tr_lower(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


def tailor(body: Any, path_params: dict, query: dict, request_body: Any) -> Any:
    """Örneği isteğe uydur: {code}, süzgeçler, gönderilen gövde."""
    if isinstance(body, dict):
        if isinstance(request_body, dict):
            body = {**body, **request_body}
        if "code" in path_params and "code" in body:
            body["code"] = str(path_params["code"]).upper()
        return body

    if isinstance(body, list) and body and all(isinstance(x, dict) for x in body):
        q = query.get("q")
        if q:
            needle = _tr_lower(q)
            body = [
                x
                for x in body
                if needle in _tr_lower(str(x.get("code", ""))) or needle in _tr_lower(str(x.get("name", "")))
            ]
        for key, value in query.items():
            if key != "q" and body and key in body[0]:
                body = [x for x in body if str(x.get(key)) == value]
    return body


# --------------------------------------------------------------------------- kayıt


def _registered(app: FastAPI) -> set[tuple[str, str]]:
    """Uygulamada zaten var olan (METOT, yol) çiftleri — FastAPI sürümünden bağımsız."""
    out = set()
    for path, ops in app.openapi().get("paths", {}).items():
        out.update((m.upper(), path) for m in ops)
    return out


def mock_operations(app: FastAPI, spec: dict) -> list[tuple[str, str, dict]]:
    """Mock'lanacak (METOT, yol, işlem) listesi: sözleşmede olup uygulamada olmayanlar."""
    existing = _registered(app)
    todo = []
    for path, ops in spec.get("paths", {}).items():
        if path.startswith(SKIP_PREFIXES) or path == "/health":
            continue
        for method, op in ops.items():
            if method in METHODS and (method.upper(), path) not in existing:
                todo.append((method.upper(), path, op))
    return todo


def _make_handler(status: int, example: Any):
    async def handler(request: Request) -> Response:
        if status == 204:
            return Response(status_code=204, headers=MOCK_HEADERS)
        try:
            sent = await request.json() if request.method in ("POST", "PUT", "PATCH") else None
        except (json.JSONDecodeError, UnicodeDecodeError):
            sent = None
        body = tailor(copy.deepcopy(example), dict(request.path_params), dict(request.query_params), sent)
        return JSONResponse(body, status_code=status, headers=MOCK_HEADERS)

    return handler


def register_mock_routes(app: FastAPI, spec: dict | None = None) -> list[str]:
    """Eksik uçları mock olarak ekler; eklenenlerin listesini döner."""
    spec = spec or load_spec()
    added = []
    for method, path, op in mock_operations(app, spec):
        status, example = pick_example(op, spec)
        app.add_api_route(
            path,
            _make_handler(status, example),
            methods=[method],
            tags=["mock"],
            summary=f"[MOCK] {op.get('summary', '')}",
            status_code=status,
        )
        added.append(f"{method} {path}")
    app.openapi_schema = None  # Swagger yeni uçları görsün
    log.warning("MOCK=1: %d uç sözleşme örnekleriyle çalışıyor", len(added))
    return added
