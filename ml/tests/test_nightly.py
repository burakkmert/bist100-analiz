"""Gece zinciri testleri: sahte adım çalıştırıcı, dosya sistemi yalnızca tmp; GPU/DB/internet gerekmez.

Çalıştırma: pytest ml/tests/test_nightly.py -q
"""
import os
import time
from datetime import date, timedelta
from pathlib import Path
import tempfile

import pandas as pd

from ml.nightly import (STEPS, acquire_lock, check_freshness, orchestrate, release_lock, run_step,
                        validate_outputs)

TODAY = date(2026, 10, 12)


def good_forecasts() -> pd.DataFrame:
    rows = []
    for code in ("A", "B"):
        for h in (1, 5, 20, 30, 120):
            rows.append({"code": code, "run_date": "2026-10-12", "model": "naive", "horizon": h,
                         "p10": 90.0, "p50": None if h == 120 else 100.0, "p90": 110.0})
    return pd.DataFrame(rows)


def good_scenarios() -> pd.DataFrame:
    return pd.DataFrame({"code": ["A", "B"], "run_date": "2026-10-12", "horizon": 30,
                         "bear": [90.0, 90.0], "base": [100.0, 100.0], "bull": [110.0, 110.0]})


# ---------------------------------------------------------------- tazelik

def test_freshness_ok_and_stale():
    ok = check_freshness({"A": TODAY - timedelta(days=3), "B": TODAY - timedelta(days=1)}, TODAY)
    assert ok["ok"] and ok["fresh_frac"] == 1.0
    stale = check_freshness({"A": TODAY - timedelta(days=30), "B": TODAY - timedelta(days=40)}, TODAY)
    assert not stale["ok"]
    assert not check_freshness({"A": None}, TODAY)["ok"]            # hiç veri yok
    long_holiday = check_freshness({"A": TODAY - timedelta(days=9)}, TODAY, max_stale_days=10)
    assert long_holiday["ok"]                                       # bayram için eşik artırılabilir


def test_freshness_tolerates_some_dead_assets():
    d = {f"S{i}": TODAY - timedelta(days=2) for i in range(8)}
    d.update({"X1": TODAY - timedelta(days=200), "X2": None})        # işlem görmeyen birkaç hisse
    assert check_freshness(d, TODAY)["ok"]


# ---------------------------------------------------------------- kilit

def test_lock_blocks_second_run_and_expires():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "nightly.lock"
        assert acquire_lock(path)
        assert not acquire_lock(path)                               # ikinci zincir giremez
        assert acquire_lock(path, now=time.time() + 7 * 3600)       # 6 saatten eski kilit ezilir
        release_lock(path)
        assert not path.exists()
        release_lock(path)                                          # olmayan kilidi silmek hata vermez
        assert acquire_lock(path)


# ---------------------------------------------------------------- son kontrol

def test_validate_ok():
    crit, warn = validate_outputs(good_forecasts(), good_scenarios(), 2)
    assert crit == [] and warn == []


def test_validate_catches_120d_point_forecast():
    f = good_forecasts()
    f.loc[f["horizon"] == 120, "p50"] = 100.0
    crit, _ = validate_outputs(f, good_scenarios(), 2)
    assert any("120g" in c for c in crit)


def test_validate_catches_bad_quantiles_and_scenarios():
    f = good_forecasts()
    f.loc[0, "p10"] = 120.0                                         # p10 > p50
    s = good_scenarios()
    s.loc[0, "base"] = 200.0                                        # base > bull
    crit, _ = validate_outputs(f, s, 2)
    assert any("kantil" in c for c in crit)
    assert any("senaryo" in c for c in crit)
    assert any("scenarios çıktısı yok" in c for c in validate_outputs(good_forecasts(), None, 2)[0])


def test_validate_warns_on_low_coverage():
    _, warn = validate_outputs(good_forecasts(), good_scenarios(), 100)
    assert len(warn) == 2


# ---------------------------------------------------------------- adım / zincir

class FakeRunner:
    """Modül adına göre önceden belirlenen dönüş kodlarını sırayla verir."""
    def __init__(self, plan: dict[str, list[int]]):
        self.plan, self.calls = plan, []

    def __call__(self, cmd, timeout_s):
        module = cmd[cmd.index("-m") + 1]
        self.calls.append((module, cmd[cmd.index("-m") + 2:]))
        codes = self.plan.get(module, [0])
        rc = codes.pop(0) if len(codes) > 1 else codes[0]
        return rc, [f"{module} rc={rc}"]


def no_sleep(_):
    pass


def test_run_step_retries_once_then_succeeds():
    r = FakeRunner({"ml.batch_forecast": [1, 0]})
    res = run_step(STEPS[0], [], r, sleep=no_sleep)
    assert res["status"] == "success" and res["attempts"] == 2


def test_run_step_gives_up_after_retry_and_not_on_timeout():
    r = FakeRunner({"ml.batch_forecast": [1]})
    res = run_step(STEPS[0], [], r, sleep=no_sleep)
    assert res["status"] == "failed" and res["attempts"] == 2 and res["tail"]
    r2 = FakeRunner({"ml.batch_forecast": [124]})
    res2 = run_step(STEPS[0], [], r2, sleep=no_sleep)
    assert res2["attempts"] == 1                                    # zaman aşımı tekrar denenmez


def test_orchestrate_all_ok_passes_paths_and_db():
    r = FakeRunner({})
    with tempfile.TemporaryDirectory() as tmp:
        rep = orchestrate(TODAY, True, None, False, r, no_sleep, 0, Path(tmp))
    assert rep["status"] == "success"
    assert [c[0] for c in r.calls] == ["ml.batch_forecast", "ml.model_errors", "ml.scenarios"]
    fa = r.calls[0][1]
    assert "--db" in fa and fa[fa.index("--run-date") + 1] == "2026-10-12"
    assert "--forecasts" in r.calls[2][1] and "--db" in r.calls[2][1]


def test_orchestrate_forecast_failure_skips_rest():
    r = FakeRunner({"ml.batch_forecast": [1]})
    with tempfile.TemporaryDirectory() as tmp:
        rep = orchestrate(TODAY, False, None, False, r, no_sleep, 0, Path(tmp))
    assert rep["status"] == "failed" and rep["failed_critical"] == ["forecast"]
    assert [s["status"] for s in rep["steps"]] == ["failed", "skipped", "skipped"]
    assert [c[0] for c in r.calls] == ["ml.batch_forecast"] * 2     # 1 deneme + 1 yeniden deneme


def test_orchestrate_model_errors_failure_is_partial():
    r = FakeRunner({"ml.model_errors": [1]})
    with tempfile.TemporaryDirectory() as tmp:
        rep = orchestrate(TODAY, False, None, False, r, no_sleep, 0, Path(tmp))
    assert rep["status"] == "partial" and rep["failed_soft"] == ["model_errors"]
    assert rep["steps"][2]["status"] == "success"                   # senaryolar yine de üretildi


def test_orchestrate_skip_model_errors_and_codes():
    r = FakeRunner({})
    with tempfile.TemporaryDirectory() as tmp:
        rep = orchestrate(TODAY, False, ["THYAO"], True, r, no_sleep, 0, Path(tmp))
    assert rep["status"] == "success" and rep["steps"][1]["status"] == "skipped"
    assert "ml.model_errors" not in [c[0] for c in r.calls]
    assert "THYAO" in r.calls[0][1]


def test_orchestrate_scenarios_failure_is_critical():
    r = FakeRunner({"ml.scenarios": [1]})
    with tempfile.TemporaryDirectory() as tmp:
        rep = orchestrate(TODAY, False, None, False, r, no_sleep, 0, Path(tmp))
    assert rep["status"] == "failed" and rep["failed_critical"] == ["scenarios"]
