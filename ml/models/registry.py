"""config.yaml'dan model nesnelerini oluşturur. Gece işi ve backtest buradan alır."""
from __future__ import annotations

from ml.models.base import Forecaster, load_config


def build_models(names: list[str] | None = None, cfg: dict | None = None) -> list[Forecaster]:
    cfg = cfg or load_config()
    m = cfg["models"]
    ctx, device = cfg["context_length"], cfg.get("device", "auto")
    spread = cfg.get("baseline_spread_window", 500)
    names = names or list(m)

    models: list[Forecaster] = []
    for name in names:
        if name == "naive":
            from ml.models.baselines import NaiveForecaster
            models.append(NaiveForecaster(spread_window=spread))
        elif name == "naive_drift":
            from ml.models.baselines import NaiveDriftForecaster
            models.append(NaiveDriftForecaster(m.get("naive_drift", {}).get("window", 250), spread))
        elif name in ("moving_average", "ma"):
            from ml.models.baselines import MovingAverageForecaster
            models.append(MovingAverageForecaster(m["moving_average"]["window"], spread))
        elif name == "arima":
            from ml.models.baselines import ArimaForecaster
            models.append(ArimaForecaster(tuple(m["arima"]["order"]), ctx, spread))
        elif name == "timesfm":
            from ml.models.timesfm_model import TimesFMForecaster
            max_h = max(cfg["horizons"])
            models.append(TimesFMForecaster(m["timesfm"]["repo"], ctx, max_horizon=-(-max_h // 128) * 128,
                                            batch_size=m["timesfm"]["batch_size"], device=device))
        elif name == "chronos":
            from ml.models.chronos_model import ChronosForecaster
            models.append(ChronosForecaster(m["chronos"]["repo"], ctx,
                                            batch_size=m["chronos"]["batch_size"], device=device))
        else:
            raise ValueError(f"Bilinmeyen model: {name}")
    return models
