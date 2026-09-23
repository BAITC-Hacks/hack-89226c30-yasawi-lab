from __future__ import annotations

import numpy as np
import pandas as pd

from .data import FarmData
from .model import DirectMultiHorizonModel


def backtest(data: FarmData, start: pd.Timestamp, horizon: int, alpha: float = 1.0) -> dict:
    """Development backtest using known weather observations.

    This is deliberately labelled as a proxy evaluation. Competition evaluation
    must replace observed future weather with archived forecast vintages.
    """
    history = data.hourly.loc[data.hourly.index < start].copy()
    future_index = pd.date_range(start, periods=horizon, freq="1h", name="timestamp")
    future = data.hourly.reindex(future_index)
    model = DirectMultiHorizonModel(horizon_hours=horizon, alpha=alpha).fit(history)
    prediction = model.forecast(history, future[["wind_speed", "temperature"]])
    actual = future["farm_power"].to_numpy(dtype=float)
    predicted = prediction["forecast_farm_power"].to_numpy(dtype=float)
    valid = np.isfinite(actual) & np.isfinite(predicted)
    if not valid.any():
        raise ValueError("Backtest window has no observed target values")
    error = predicted[valid] - actual[valid]
    denominator = max(float(np.abs(actual[valid]).sum()), 1e-9)
    return {
        "evaluation_type": "proxy_backtest_with_observed_future_weather",
        "start": start.isoformat(),
        "horizon_hours": horizon,
        "valid_targets": int(valid.sum()),
        "mae": float(np.abs(error).mean()),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "wmape": float(np.abs(error).sum() / denominator),
        "actual_mean": float(actual[valid].mean()),
        "prediction_mean": float(predicted[valid].mean()),
    }
