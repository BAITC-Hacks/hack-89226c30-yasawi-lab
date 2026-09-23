from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


FEATURE_NAMES = [
    "power_lag_1", "power_lag_2", "power_lag_3", "power_lag_6",
    "power_lag_12", "power_lag_24", "power_lag_48", "power_roll_6",
    "power_roll_24", "wind_speed", "wind_power_curve", "temperature",
    "hour_sin", "hour_cos", "dow_sin", "dow_cos", "horizon_sin", "horizon_cos",
]
LAGS = (1, 2, 3, 6, 12, 24, 48)


def _calendar_features(timestamp: pd.Timestamp, horizon: int) -> list[float]:
    hour = timestamp.hour + timestamp.minute / 60
    dow = timestamp.dayofweek
    return [
        np.sin(2 * np.pi * hour / 24), np.cos(2 * np.pi * hour / 24),
        np.sin(2 * np.pi * dow / 7), np.cos(2 * np.pi * dow / 7),
        np.sin(2 * np.pi * horizon / 48), np.cos(2 * np.pi * horizon / 48),
    ]


def make_feature_row(history: pd.DataFrame, timestamp: pd.Timestamp, horizon: int, weather_row: pd.Series) -> np.ndarray:
    power = history["farm_power"]
    values = [power.iloc[-lag] for lag in LAGS]
    values += [power.iloc[-6:].mean(), power.iloc[-24:].mean()]
    wind = float(weather_row["wind_speed"])
    values += [wind, np.clip(wind, 0.0, 25.0) ** 3, float(weather_row["temperature"])]
    values += _calendar_features(timestamp, horizon)
    return np.asarray(values, dtype=float)


def _training_rows(frame: pd.DataFrame, horizon: int) -> tuple[np.ndarray, np.ndarray]:
    # The reindexed frame makes positional offsets equal real hours. Build the
    # supervised matrix with NumPy so all 48 horizon models remain fast enough
    # for daily agentic replay.
    power = frame["farm_power"].to_numpy(dtype=float)
    wind = frame["wind_speed"].to_numpy(dtype=float)
    temperature = frame["temperature"].to_numpy(dtype=float)
    origins = np.arange(48, len(frame) - horizon)
    targets = power[origins + horizon]
    valid = np.isfinite(targets) & np.isfinite(power[origins - 48])
    for lag in LAGS:
        valid &= np.isfinite(power[origins - lag])
    valid &= np.isfinite(wind[origins + horizon]) & np.isfinite(temperature[origins + horizon])
    origins = origins[valid]
    targets = targets[valid]
    if len(origins) == 0:
        return np.empty((0, len(FEATURE_NAMES))), np.empty(0)
    roll6 = pd.Series(power).rolling(6, min_periods=6).mean().to_numpy()
    roll24 = pd.Series(power).rolling(24, min_periods=24).mean().to_numpy()
    timestamps = frame.index[origins + horizon]
    hour = timestamps.hour.to_numpy() + timestamps.minute.to_numpy() / 60
    dow = timestamps.dayofweek.to_numpy()
    rows = np.column_stack([
        *[power[origins - lag] for lag in LAGS],
        roll6[origins], roll24[origins],
        wind[origins + horizon], np.clip(wind[origins + horizon], 0.0, 25.0) ** 3,
        temperature[origins + horizon],
        np.sin(2 * np.pi * hour / 24), np.cos(2 * np.pi * hour / 24),
        np.sin(2 * np.pi * dow / 7), np.cos(2 * np.pi * dow / 7),
        np.full(len(origins), np.sin(2 * np.pi * horizon / 48)),
        np.full(len(origins), np.cos(2 * np.pi * horizon / 48)),
    ])
    valid_rows = np.isfinite(rows).all(axis=1)
    return rows[valid_rows], targets[valid_rows]


@dataclass
class DirectMultiHorizonModel:
    horizon_hours: int = 48
    alpha: float = 1.0
    models_: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray, float]] | None = None
    sample_counts_: dict[int, int] | None = None

    def fit(self, frame: pd.DataFrame) -> "DirectMultiHorizonModel":
        self.models_ = {}
        self.sample_counts_ = {}
        for horizon in range(1, self.horizon_hours + 1):
            x, y = _training_rows(frame, horizon)
            if len(x) < 100:
                continue
            mean = x.mean(axis=0)
            scale = x.std(axis=0)
            scale[scale < 1e-8] = 1.0
            z = (x - mean) / scale
            design = np.column_stack([np.ones(len(z)), z])
            penalty = np.eye(design.shape[1]) * self.alpha
            penalty[0, 0] = 0.0
            solution = np.linalg.solve(design.T @ design + penalty, design.T @ y)
            self.models_[horizon] = (mean, scale, solution[1:], solution[0])
            self.sample_counts_[horizon] = len(x)
        if len(self.models_) < self.horizon_hours:
            raise ValueError("Not enough complete hourly training history for all horizons")
        return self

    def _predict_one(self, row: np.ndarray, horizon: int) -> float:
        if self.models_ is None:
            raise RuntimeError("Model must be fitted before prediction")
        mean, scale, weights, bias = self.models_[horizon]
        return float(np.clip(bias + ((row - mean) / scale) @ weights, 0.0, 2.0))

    def forecast(self, history: pd.DataFrame, weather: pd.DataFrame) -> pd.DataFrame:
        if self.models_ is None:
            raise RuntimeError("Model must be fitted before prediction")
        history = history[["farm_power", "wind_speed", "temperature"]].copy()
        predictions = []
        for horizon, (timestamp, weather_row) in enumerate(weather.iterrows(), start=1):
            row = make_feature_row(history, timestamp, horizon, weather_row)
            prediction = self._predict_one(row, horizon)
            predictions.append(prediction)
            # Recursive history is used only to construct lagged target features.
            history.loc[timestamp, "farm_power"] = prediction
            history.loc[timestamp, "wind_speed"] = weather_row["wind_speed"]
            history.loc[timestamp, "temperature"] = weather_row["temperature"]
        result = weather.copy()
        result["forecast_farm_power"] = predictions
        return result


# Backward-compatible name for callers of the first implementation.
RidgeForecastModel = DirectMultiHorizonModel
