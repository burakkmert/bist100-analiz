"""TimesFM 2.5 (200M) sarmalayıcısı — sıfır atış, eğitim yok.

Model bir kez yüklenir ve derlenir; tüm seriler batch'ler hâlinde verilir.
Çıktı kantilleri: quantile_forecast[..., k] -> k=0 ortalama, k=1 q10, ..., k=9 q90.
"""
from __future__ import annotations

import numpy as np

from ml.models.base import Forecaster, batched, quantiles_to_frame, resolve_device

Q_IDX = [1, 5, 9]  # q10, q50, q90


class TimesFMForecaster(Forecaster):
    name = "timesfm"

    def __init__(self, repo: str = "google/timesfm-2.5-200m-pytorch", context_length: int = 512,
                 max_horizon: int = 128, batch_size: int = 64, device: str = "auto", model=None):
        self.repo = repo
        self.context_length = context_length
        self.max_horizon = max_horizon
        self.batch_size = batch_size
        self.device = resolve_device(device)
        self._model = model  # testlerde sahte model verilebilir

    def _load(self):
        if self._model is not None:
            return self._model
        import timesfm
        import torch

        if self.device == "cuda":
            torch.set_float32_matmul_precision("high")
        model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
            self.repo,
            torch_compile=False,  # Windows'ta torch.compile Triton ister
        )
        model.compile(timesfm.ForecastConfig(
            max_context=self.context_length,
            max_horizon=self.max_horizon,
            normalize_inputs=True,
            per_core_batch_size=self.batch_size,
            use_continuous_quantile_head=True,
            force_flip_invariance=True,
            infer_is_positive=True,     # fiyatlar pozitif
            fix_quantile_crossing=True,
        ))
        self._model = model
        return model

    def _predict(self, series, horizons):
        max_h = max(horizons)
        if max_h > self.max_horizon:
            raise ValueError(f"En büyük ufuk {max_h} > max_horizon {self.max_horizon}")
        model = self._load()
        codes = list(series)
        parts = []
        for chunk in batched(codes, self.batch_size):
            inputs = [series[c][-self.context_length:].copy() for c in chunk]
            _, q = model.forecast(horizon=max_h, inputs=inputs)
            parts.append(np.asarray(q)[: len(chunk), :max_h][..., Q_IDX])
        return quantiles_to_frame(codes, np.concatenate(parts), horizons)
