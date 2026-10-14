from app.ai.eval.chart_eval import TRENDS, make_series, report, score


def test_ornekler_belirleyici_ve_dengeli():
    a, b = make_series(4), make_series(4)
    assert a == b  # aynı tohum → aynı grafik (tekrar üretilebilir değerlendirme)
    assert [make_series(i)["trend"] for i in range(6)] == list(TRENDS) * 2
    up, down = make_series(0)["closes"], make_series(1)["closes"]
    assert up[-1] > up[0] and down[-1] < down[0]


def test_yatay_seviye_isabeti():
    s = make_series(2)
    t = s["truth"]
    ok = score(s, {"trend": "flat", "supports": [t["support"] * 1.01], "resistances": [t["resistance"] * 0.99]})
    assert ok["trend_ok"] and ok["support_hit"] and ok["resistance_hit"] and ok["levels_plausible"] == 2
    bad = score(s, {"trend": "up", "supports": [t["support"] * 0.5], "resistances": []})
    assert not bad["trend_ok"] and not bad["support_hit"] and bad["levels_plausible"] == 0


def test_rapor_tablosu():
    s = make_series(0)
    row = {"id": s["id"], "mode": "image", "trend": "up", "seconds": 2.0, "provider": "fake", "model": None,
           "out": {"trend": "up", "supports": [], "resistances": []}, **score(s, {"trend": "up"})}
    md = report([row], 1)
    assert "Yalnızca görüntü" in md and "%100 (1/1)" in md
