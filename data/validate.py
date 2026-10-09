"""Veri kalite raporu (Görev 3).

Her varlık için: satır sayısı, ilk/son gün, güncel mi, eksik gün sayısı, sıçrama sayısı,
`min_history_ok` (>= 120 işlem günü). Sonuçta tek bir gece raporu (JSON) üretilir;
Kişi 2 bu özeti `job_runs.stats` alanına yazabilir.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from data.cleaning import clean_prices, market_calendar, missing_days

MIN_HISTORY_DAYS = 120
REPORT_DIR = Path(__file__).resolve().parent / "cache" / "reports"


def expected_last_date(frames: list[pd.DataFrame], min_share: float = 0.2):
    """Beklenen son işlem günü: varlıkların en az %20'sinin ulaştığı en geç gün.
    (Tek bir hatalı varlık 'yarının' tarihini taşısa bile herkes eski görünmesin.)"""
    lasts = sorted((max(f["date"]) for f in frames if not f.empty), reverse=True)
    if not lasts:
        return None
    k = max(1, int(len(lasts) * min_share))
    return lasts[k - 1]


def validate_assets(frames: dict[str, pd.DataFrame], asset_types: dict[str, str] | None = None,
                    min_history: int = MIN_HISTORY_DAYS) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame]:
    """frames: {kod: fiyat tablosu}. Dönüş: (temiz tablolar, varlık özeti, tüm sorunlar).

    Hisse ve fon takvimleri ayrı hesaplanır (fonlar bazı günler hisselerden farklı işler)."""
    asset_types = asset_types or {}
    # Hisse takvimi sıçrama eşiği için gerekir (eksik veri gününde eşik genişler)
    stock_cal = market_calendar([f for c, f in frames.items()
                                 if asset_types.get(c, "stock") == "stock" and not f.empty])
    cleaned, all_issues = {}, []
    for code, df in frames.items():
        kind = asset_types.get(code, "stock")
        cleaned[code], issues = clean_prices(df, asset_type=kind,
                                             calendar=stock_cal if kind == "stock" else None)
        all_issues.append(issues)

    calendars = {}
    for kind in {asset_types.get(c, "stock") for c in cleaned}:
        calendars[kind] = market_calendar([f for c, f in cleaned.items() if asset_types.get(c, "stock") == kind])

    expected = {kind: expected_last_date([f for c, f in cleaned.items()
                                           if asset_types.get(c, "stock") == kind])
                for kind in calendars}

    rows = []
    for code, df in cleaned.items():
        cal = calendars[asset_types.get(code, "stock")]
        expected_last = expected[asset_types.get(code, "stock")]
        last = max(df["date"]) if not df.empty else None
        issues = all_issues[list(cleaned).index(code)]
        rows.append({
            "code": code,
            "type": asset_types.get(code, "stock"),
            "rows": len(df),
            "first_date": min(df["date"]) if not df.empty else None,
            "last_date": last,
            "up_to_date": bool(last is not None and expected_last is not None and last >= expected_last),
            "missing_days": len(missing_days(df, cal)),
            "jumps": int((issues["issue"] == "jump").sum()),
            "nonpositive": int((issues["issue"] == "nonpositive_price").sum()),
            "min_history_ok": len(df) >= min_history,
        })
    issues_df = pd.concat(all_issues, ignore_index=True) if all_issues else pd.DataFrame()
    return cleaned, pd.DataFrame(rows), issues_df


def build_report(summary: pd.DataFrame, collect_errors: list[str], run_date: date | None = None) -> dict:
    """Gece raporu: Kişi 2'nin job_runs.stats alanına uygun düz bir sözlük."""
    s = summary
    return {
        "run_date": (run_date or date.today()).isoformat(),
        "assets_total": int(len(s)),
        "stocks": int((s["type"] == "stock").sum()) if len(s) else 0,
        "funds": int((s["type"] == "fund").sum()) if len(s) else 0,
        "up_to_date": int(s["up_to_date"].sum()) if len(s) else 0,
        "stale": sorted(s.loc[~s["up_to_date"], "code"].tolist()) if len(s) else [],
        "collect_errors": sorted(collect_errors),
        "short_history": sorted(s.loc[~s["min_history_ok"], "code"].tolist()) if len(s) else [],
        "with_jumps": sorted(s.loc[s["jumps"] > 0, "code"].tolist()) if len(s) else [],
        "missing_days_total": int(s["missing_days"].sum()) if len(s) else 0,
    }


def write_report(report: dict, summary: pd.DataFrame, issues: pd.DataFrame, out_dir: Path = REPORT_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"quality_{report['run_date']}"
    (out_dir / f"{stem}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary.to_csv(out_dir / f"{stem}_assets.csv", index=False)
    issues.to_csv(out_dir / f"{stem}_issues.csv", index=False)
    return out_dir / f"{stem}.json"
