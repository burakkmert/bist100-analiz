"""Veritabanı kaynakları: yapay zekâ katmanının Kişi 1/Kişi 2 tablolarını okuması ve ai_explanations'a yazması.

• DbAnalysisSource   → sohbet ve grafik okuma için analysis + prices (yalnızca OKUR)
• DbExplainSource    → gece yorum işi için hedefler (analysis + signals + watchlist, yalnızca OKUR)
• DbExplanationSink  → ai_explanations'a upsert (bu tablonun tek yazanı Kişi 3)

SQLAlchemy yalnızca bu modül kullanılınca içe aktarılır; böylece yerel geliştirme sunucusu
(dev_server, veritabanı yok) bu dosyaya hiç dokunmadan çalışır. Oturum fabrikası dışarıdan verilir:
uygulamada `from_app()` Kişi 2'nin `app.core.db.SessionLocal`'ını kullanır, testlerde başka bir fabrika verilir.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Iterable
from datetime import date
from typing import Any

from .explain_job import Explanation, Target

log = logging.getLogger("app.ai.db")

SessionFactory = Callable[[], Any]  # çağrılınca SQLAlchemy Session döner


def _app_session_factory() -> SessionFactory:
    from app.core.db import SessionLocal  # Kişi 2'nin bağlantısı (DATABASE_URL)

    return SessionLocal


def _date(v: str | date) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v))


def _iso(v: Any) -> Any:
    return v.isoformat() if isinstance(v, date) else v


def _num(v: Any) -> Any:
    """Decimal → float (JSON'a ve isteme düz sayı olarak gitsin)."""
    if v is None or isinstance(v, (int, float, bool)):
        return v
    try:
        return float(v)
    except (TypeError, ValueError):
        return v


def analysis_row_to_dict(r: dict[str, Any]) -> dict[str, Any]:
    """analysis satırı → openapi'deki Analysis şekli (low/mid/high → range)."""
    return {
        "code": r["code"],
        "run_date": _iso(r["run_date"]),
        "horizon": int(r["horizon"]),
        "direction": r.get("direction"),
        "confidence": r.get("confidence"),
        "risk": r.get("risk"),
        "regime": r.get("regime"),
        "range": {"low": _num(r.get("low")), "mid": _num(r.get("mid")), "high": _num(r.get("high"))},
        "weights": r.get("weights"),
        "indicators": r.get("indicators"),
        "asset_type": r.get("asset_type"),  # güven yorumu için (yalnızca fonlarda anlamlı)
    }


class _Db:
    def __init__(self, session_factory: SessionFactory):
        self._sf = session_factory

    def _rows(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        from sqlalchemy import text

        with self._sf() as s:
            return [dict(r) for r in s.execute(text(sql), params).mappings().all()]


# ---- Sohbet ve grafik okuma -------------------------------------------------------------------------


class DbAnalysisSource(_Db):
    """context.AnalysisSource'un veritabanı sürümü. Hata olursa None döner; sohbet veri olmadan sürer."""

    @classmethod
    def from_app(cls) -> DbAnalysisSource:
        return cls(_app_session_factory())

    def _analysis(self, code: str, horizon: int) -> dict[str, Any] | None:
        rows = self._rows(
            """SELECT a.code, a.run_date, a.horizon, a.direction, a.confidence, a.risk, a.regime, a.weights, a.indicators,
                      a.low, a.mid, a.high, s.type AS asset_type
               FROM analysis a JOIN assets s ON s.code = a.code
               WHERE a.code = :code AND a.horizon = :h ORDER BY a.run_date DESC LIMIT 1""",
            {"code": code.upper(), "h": horizon},
        )
        return analysis_row_to_dict(rows[0]) if rows else None

    def _prices(self, code: str, days: int) -> list[dict[str, Any]] | None:
        # Kişi 1: her zaman COALESCE(adj_close, close). Hisselerde adj_close bedelsiz/hata düzeltilmiş fiyattır;
        # tahmin ve senaryolar bu seriden üretildiği için model aynı seriyi görmeli. Fonlarda adj_close = close.
        rows = self._rows(
            "SELECT date, COALESCE(adj_close, close) AS price FROM prices WHERE code = :code ORDER BY date DESC LIMIT :n",
            {"code": code.upper(), "n": days},
        )
        if not rows:
            return None
        rows.reverse()  # eskiden yeniye
        return [{"date": _iso(r["date"]), "close": _num(r["price"])} for r in rows]

    async def get_analysis(self, code: str, horizon: int = 5) -> dict[str, Any] | None:
        try:
            return await asyncio.to_thread(self._analysis, code, horizon)
        except Exception as e:  # tablo yok, bağlantı yok…: kullanıcıya hata gösterme, veri yok say
            log.warning("analysis okunamadı (%s/%s): %r", code, horizon, e)
            return None

    async def get_recent_prices(self, code: str, days: int = 120) -> list[dict[str, Any]] | None:
        try:
            return await asyncio.to_thread(self._prices, code, days)
        except Exception as e:
            log.warning("prices okunamadı (%s): %r", code, e)
            return None


# ---- Gece uzman yorumları -----------------------------------------------------------------------------


class DbExplainSource(_Db):
    """explain_job.ExplainSource: en son run_date'in analysis satırları.

    LLM yalnızca sinyali olan (o gün oluşturulmuş) ya da en az bir kullanıcının izlediği varlıklara gider;
    diğerleri şablon metin alır (ücretsiz kota için).
    """

    def __init__(self, session_factory: SessionFactory, run_date: str | None = None):
        super().__init__(session_factory)
        self.run_date = run_date

    @classmethod
    def from_app(cls, run_date: str | None = None) -> DbExplainSource:
        return cls(_app_session_factory(), run_date)

    def resolve_run_date(self) -> str | None:
        if self.run_date:
            return self.run_date
        rows = self._rows("SELECT MAX(run_date) AS d FROM analysis", {})
        return _iso(rows[0]["d"]) if rows and rows[0]["d"] else None

    def targets(self) -> Iterable[Target]:
        d = self.resolve_run_date()
        if not d:
            return []
        analyses = self._rows(
            """SELECT a.code, a.run_date, a.horizon, a.direction, a.confidence, a.risk, a.regime, a.weights, a.indicators,
                      a.low, a.mid, a.high, s.type AS asset_type
               FROM analysis a JOIN assets s ON s.code = a.code
               WHERE a.run_date = :d ORDER BY a.code, a.horizon""",
            {"d": _date(d)},
        )
        signaled = {r["code"] for r in self._rows("SELECT DISTINCT code FROM signals WHERE CAST(created_at AS date) >= :d", {"d": _date(d)})}
        watched = {r["code"] for r in self._rows("SELECT DISTINCT code FROM watchlist", {})}
        return [
            Target(analysis=analysis_row_to_dict(r), has_signal=r["code"] in signaled, watched=r["code"] in watched)
            for r in analyses
        ]


class DbExplanationSink(_Db):
    """ai_explanations'a upsert: aynı (code, run_date, horizon) varsa metin güncellenir."""

    @classmethod
    def from_app(cls) -> DbExplanationSink:
        return cls(_app_session_factory())

    def save(self, rows: list[Explanation]) -> None:
        if not rows:
            return
        from sqlalchemy import text

        sql = text(
            """INSERT INTO ai_explanations (code, run_date, horizon, text)
               VALUES (:code, :run_date, :horizon, :text)
               ON CONFLICT (code, run_date, horizon) DO UPDATE SET text = EXCLUDED.text"""
        )
        with self._sf() as s:
            s.execute(sql, [{"code": r.code, "run_date": _date(r.run_date), "horizon": r.horizon, "text": r.text} for r in rows])
            s.commit()
