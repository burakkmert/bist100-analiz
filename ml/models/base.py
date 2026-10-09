"""Ortak tahmin arayüzü (Görev 4).

Her model aynı girdiyi alır ve aynı biçimde döndürür; böylece gece işi ve backtest
modelden bağımsız yazılır.

    girdi : {kod: fiyat dizisi (eskiden yeniye, 1-B)}
    çıktı : DataFrame[code, horizon, p10, p50, p90]   (fiyat seviyesinde)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np
import pandas as pd

OUTPUT_COLUMNS = ["code", "horizon", "p10", "p50", "p90"]
CONFIG_FILE = Path(__file__).resolve().parent.parent / "config.yaml"


def load_config(path: Path = CONFIG_FILE) -> dict:
    import yaml

    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_device(device: str = "auto") -> str:
    if device != "auto":
        return device
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


def clean_series(values) -> np.ndarray:
    """NaN ve sıfır/negatif değerleri atar, float32 1-B dizi döndürür."""
    arr = np.asarray(values, dtype="float64").ravel()
    arr = arr[np.isfinite(arr) & (arr > 0)]
    return arr.astype("float32")


def fix_quantile_order(df: pd.DataFrame) -> pd.DataFrame:
    """Kantil çaprazlamasını düzeltir: her satırda p10 <= p50 <= p90 garanti."""
    q = np.sort(df[["p10", "p50", "p90"]].to_numpy(dtype="float64"), axis=1)
    df[["p10", "p50", "p90"]] = q
    return df


class Forecaster(ABC):
    """Tüm modellerin uyduğu arayüz."""

    name: str = "base"

    def predict(self, series: dict[str, np.ndarray], horizons: list[int]) -> pd.DataFrame:
        """series: {code: fiyat dizisi}. Dönüş: code, horizon, p10, p50, p90."""
        clean = {code: clean_series(v) for code, v in series.items()}
        clean = {code: v for code, v in clean.items() if len(v) >= 2}
        if not clean:
            return pd.DataFrame(columns=OUTPUT_COLUMNS)
        horizons = sorted(set(int(h) for h in horizons))
        out = self._predict(clean, horizons)
        out = out[OUTPUT_COLUMNS].sort_values(["code", "horizon"]).reset_index(drop=True)
        return fix_quantile_order(out)

    @abstractmethod
    def _predict(self, series: dict[str, np.ndarray], horizons: list[int]) -> pd.DataFrame:
        """Alt sınıflar uygular; girdiler temizlenmiş ve en az 2 noktalıdır."""


def quantiles_to_frame(codes: list[str], q: np.ndarray, horizons: list[int]) -> pd.DataFrame:
    """q: (seri sayısı, max_h, 3) dizisinden istenen ufukları seçip tabloya çevirir."""
    rows = []
    for i, code in enumerate(codes):
        for h in horizons:
            p10, p50, p90 = (float(x) for x in q[i, h - 1])
            rows.append({"code": code, "horizon": h, "p10": p10, "p50": p50, "p90": p90})
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)


def batched(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]
