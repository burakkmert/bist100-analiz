"""Chronos-2 sarmalayıcısı — sıfır atış, eğitim yok.

predict_quantiles dönüşü: liste, her eleman (değişken sayısı=1, ufuk, kantil sayısı).
"""
from __future__ import annotations

import numpy as np

from ml.models.base import Forecaster, batched, quantiles_to_frame, resolve_device

QUANTILES = [0.1, 0.5, 0.9]


class ChronosForecaster(Forecaster):
    name = "chronos"

    def __init__(self, repo: str = "amazon/chronos-2", context_length: int = 512,
                 batch_size: int = 128, device: str = "auto", pipeline=None):
        self.repo = repo
        self.context_length = context_length
        self.batch_size = batch_size
        self.device = resolve_device(device)
        self._pipe = pipeline  # testlerde sahte pipeline verilebilir

    def _load(self):
        if self._pipe is not None:
            return self._pipe
        import torch
        from chronos import Chronos2Pipeline

        self._pipe = Chronos2Pipeline.from_pretrained(
            self.repo, device_map=self.device, torch_dtype=torch.float32)
        return self._pipe

    def _predict(self, series, horizons):
        max_h = max(horizons)
        pipe = self._load()
        codes = list(series)
        parts = []
        for chunk in batched(codes, self.batch_size):
            inputs = [series[c][-self.context_length:] for c in chunk]
            quantiles, _ = pipe.predict_quantiles(
                inputs, prediction_length=max_h, quantile_levels=QUANTILES, batch_size=self.batch_size)
            for q in quantiles:
                q = q.detach().cpu().numpy() if hasattr(q, "detach") else np.asarray(q)
                parts.append(q[0, :max_h, :])  # tek değişken
        return quantiles_to_frame(codes, np.stack(parts), horizons)
