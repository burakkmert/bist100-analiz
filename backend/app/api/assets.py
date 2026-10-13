"""Piyasa verisi uçları (Görev 4): /assets, /assets/{code}/history|forecast|analysis, /screener.

Kişi 1'in tabloları (assets, prices, forecasts, scenarios) ve karar motorunun analysis tablosu
yalnızca OKUNUR. Sorgular PK indekslerini kullanır: her varlık için yalnızca son satırlar okunur,
~1 milyon satırlık prices tablosu taranmaz.

MOCK=1 iken bu router eklenmez; aynı uçlar shared/openapi.yaml örnekleriyle cevap verir (app/api/mock.py).
"""

from __future__ import annotations

import time
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.db import get_db
from app.schemas.assets import Analysis, AssetListItem, Forecast, PricePoint

router = APIRouter(tags=["assets"], dependencies=[Depends(get_current_user)])

NOT_FOUND = {404: {"description": "Bulunamadı"}, 401: {"description": "Giriş gerekli"}}
SHORT_HORIZONS = (1, 5, 20)
LIST_CACHE_SECONDS = 60

# Türkçe arama: İ/I/ı/i hepsi "i" sayılır (iş ↔ İŞ ↔ IS)
_TR_FOLD_SQL = "lower(translate({col}, 'İIı', 'iii'))"


def _fold(q: str) -> str:
    return q.translate(str.maketrans({"İ": "i", "I": "i", "ı": "i"})).lower()


def _num(v: Any) -> float | None:
    return None if v is None else float(v)


# --------------------------------------------------------------------------- /assets


_LIST_SQL = f"""
SELECT a.code, a.name, a.type, a.sector, p.last_price,
       round(((p.px / NULLIF(p.prev_px, 0)) - 1) * 100, 4) AS change_pct
FROM assets a
JOIN LATERAL (
    SELECT (array_agg(t.close ORDER BY t.date DESC))[1] AS last_price,
           (array_agg(t.px    ORDER BY t.date DESC))[1] AS px,
           (array_agg(t.px    ORDER BY t.date DESC))[2] AS prev_px
    FROM (SELECT date, close, COALESCE(adj_close, close) AS px
          FROM prices WHERE code = a.code ORDER BY date DESC LIMIT 2) t
) p ON p.last_price IS NOT NULL
WHERE a.is_active
  AND a.type = ANY(CAST(:types AS text[]))
  AND (CAST(:q AS text) = '' OR {_TR_FOLD_SQL.format(col="a.code")} LIKE CAST(:q AS text) || '%'
               OR {_TR_FOLD_SQL.format(col="a.name")} LIKE '%' || CAST(:q AS text) || '%')
ORDER BY a.code
"""

_list_cache: dict[tuple, tuple[float, list[AssetListItem]]] = {}


def list_assets(db: Session, types: tuple[str, ...], q: str = "") -> list[AssetListItem]:
    """Son fiyat ve günlük değişimle varlık listesi. Aramasız listeler 60 sn önbelleklenir
    (veri günde bir kez, gece güncellenir)."""
    key = (types, q)
    hit = _list_cache.get(key)
    if hit and time.monotonic() - hit[0] < LIST_CACHE_SECONDS:
        return hit[1]
    rows = db.execute(text(_LIST_SQL), {"types": list(types), "q": _fold(q)}).mappings()
    items = [
        AssetListItem(
            code=r["code"],
            name=r["name"],
            type=r["type"],
            sector=r["sector"],
            last_price=float(r["last_price"]),
            change_pct=_num(r["change_pct"]),
        )
        for r in rows
    ]
    if not q:
        _list_cache[key] = (time.monotonic(), items)
    return items


def _types(type_: str | None) -> tuple[str, ...]:
    # Boşsa hisse + fon; endeks (XU100) yalnızca açıkça istenince
    return (type_,) if type_ else ("stock", "fund")


@router.get("/assets", response_model=list[AssetListItem], responses=NOT_FOUND)
def get_assets(
    type: Literal["stock", "fund", "index"] | None = None,
    q: str = Query("", max_length=50, description="Kod veya ad araması (Türkçe harf duyarsız)"),
    db: Session = Depends(get_db),
):
    return list_assets(db, _types(type), q.strip())


def _asset_exists(db: Session, code: str) -> dict:
    row = db.execute(text("SELECT code, type FROM assets WHERE code = :c"), {"c": code}).mappings().first()
    if row is None:
        raise HTTPException(404, "Varlık bulunamadı")
    return dict(row)


# --------------------------------------------------------------------------- /history


@router.get("/assets/{code}/history", response_model=list[PricePoint], responses=NOT_FOUND)
def get_history(
    code: str,
    days: int = Query(365, ge=1, le=1825, description="Son N takvim günü"),
    db: Session = Depends(get_db),
):
    code = code.upper()
    _asset_exists(db, code)
    rows = db.execute(
        text(
            """
            SELECT date, open, high, low, close, adj_close, volume FROM prices
            WHERE code = :c
              AND date > (SELECT max(date) FROM prices WHERE code = :c)
                         - make_interval(days => CAST(:d AS integer))
            ORDER BY date
            """
        ),
        {"c": code, "d": days},
    ).mappings()
    return [
        PricePoint(
            date=r["date"],
            open=_num(r["open"]),
            high=_num(r["high"]),
            low=_num(r["low"]),
            close=float(r["close"]),
            adj_close=_num(r["adj_close"]),
            volume=r["volume"],
        )
        for r in rows
    ]


# --------------------------------------------------------------------------- /forecast


@router.get("/assets/{code}/forecast", response_model=Forecast, responses=NOT_FOUND)
def get_forecast(code: str, db: Session = Depends(get_db)):
    code = code.upper()
    _asset_exists(db, code)
    run_date: date | None = db.execute(
        text("SELECT max(run_date) FROM forecasts WHERE code = :c"), {"c": code}
    ).scalar()
    if run_date is None:
        raise HTTPException(404, "Bu varlık için tahmin yok")

    bands = []
    # Karar motorunun ensemble aralığı (analysis.low/mid/high) — aynı gece çalışmasından
    for r in db.execute(
        text(
            "SELECT horizon, low, mid, high FROM analysis "
            "WHERE code = :c AND run_date = :d AND low IS NOT NULL AND high IS NOT NULL ORDER BY horizon"
        ),
        {"c": code, "d": run_date},
    ).mappings():
        bands.append(
            {
                "model": "ensemble",
                "horizon": r["horizon"],
                "p10": float(r["low"]),
                "p50": _num(r["mid"]),
                "p90": float(r["high"]),
            }
        )
    for r in db.execute(
        text(
            "SELECT model, horizon, p10, p50, p90 FROM forecasts "
            "WHERE code = :c AND run_date = :d AND p10 IS NOT NULL AND p90 IS NOT NULL "
            "ORDER BY model, horizon"
        ),
        {"c": code, "d": run_date},
    ).mappings():
        bands.append(
            {
                "model": r["model"],
                "horizon": r["horizon"],
                "p10": float(r["p10"]),
                "p50": _num(r["p50"]),
                "p90": float(r["p90"]),
            }
        )

    scenarios = [
        {
            "horizon": r["horizon"],
            "bear": float(r["bear"]),
            "base": float(r["base"]),
            "bull": float(r["bull"]),
        }
        for r in db.execute(
            text(
                "SELECT horizon, bear, base, bull FROM scenarios "
                "WHERE code = :c AND run_date = (SELECT max(run_date) FROM scenarios WHERE code = :c) "
                "AND bear IS NOT NULL AND base IS NOT NULL AND bull IS NOT NULL ORDER BY horizon"
            ),
            {"c": code},
        ).mappings()
    ]
    return Forecast(code=code, run_date=run_date, bands=bands, scenarios=scenarios)


# --------------------------------------------------------------------------- /analysis


@router.get("/assets/{code}/analysis", response_model=Analysis, responses=NOT_FOUND)
def get_analysis(
    code: str,
    horizon: Literal[1, 5, 20] = 5,
    db: Session = Depends(get_db),
):
    code = code.upper()
    _asset_exists(db, code)
    r = (
        db.execute(
            text(
                """
                SELECT a.*, e.text AS comment FROM analysis a
                LEFT JOIN ai_explanations e
                  ON e.code = a.code AND e.run_date = a.run_date AND e.horizon = a.horizon
                WHERE a.code = :c AND a.horizon = :h
                ORDER BY a.run_date DESC LIMIT 1
                """
            ),
            {"c": code, "h": horizon},
        )
        .mappings()
        .first()
    )
    if r is None:
        raise HTTPException(404, "Bu varlık için analiz yok")
    return Analysis(
        code=r["code"],
        run_date=r["run_date"],
        horizon=r["horizon"],
        range={"low": _num(r["low"]), "mid": _num(r["mid"]), "high": _num(r["high"])},
        direction=r["direction"],
        confidence=r["confidence"],
        risk=r["risk"],
        regime=r["regime"],
        weights=r["weights"],
        indicators=r["indicators"],
        comment=r["comment"],
    )


# --------------------------------------------------------------------------- /screener


@router.get("/screener", response_model=list[AssetListItem], responses=NOT_FOUND)
def screener(
    type: Literal["stock", "fund"] | None = None,
    direction: Literal["up", "down", "flat"] | None = None,
    min_conf: int = Query(0, ge=0, le=100),
    horizon: Literal[1, 5, 20] = 5,
    db: Session = Depends(get_db),
):
    """Son gece çalışmasının analizine göre süzülmüş varlıklar; güven skoruna göre azalan sıralı."""
    rows = db.execute(
        text(
            """
            SELECT code, confidence FROM analysis
            WHERE horizon = :h
              AND run_date = (SELECT max(run_date) FROM analysis WHERE horizon = :h)
              AND (CAST(:dir AS text) IS NULL OR direction = CAST(:dir AS text))
              AND COALESCE(confidence, 0) >= :mc
            """
        ),
        {"h": horizon, "dir": direction, "mc": min_conf},
    ).all()
    conf = {r.code: r.confidence or 0 for r in rows}
    if not conf:
        return []
    items = [a for a in list_assets(db, _types(type)) if a.code in conf]
    return sorted(items, key=lambda a: (-conf[a.code], a.code))
