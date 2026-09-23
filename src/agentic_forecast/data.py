from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class FarmData:
    hourly: pd.DataFrame
    turbines: list[pd.DataFrame]
    source_files: list[str]


def _read_turbine(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path)
    if len(raw.columns) < 5:
        raise ValueError(f"Expected five columns in {path.name}, found {list(raw.columns)}")
    df = raw.iloc[:, :5].copy()
    df.columns = ["id", "timestamp", "wind_speed", "power", "temperature"]
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    for column in ("wind_speed", "power", "temperature"):
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
    return df.set_index("timestamp")[["wind_speed", "power", "temperature"]]


def _complete_hourly(turbine: pd.DataFrame, index: pd.DatetimeIndex) -> pd.DataFrame:
    """Aggregate to hours without silently closing gaps in the time axis."""
    hourly = turbine.resample("1h").mean(numeric_only=True).reindex(index)
    hourly["is_missing"] = hourly[["wind_speed", "power", "temperature"]].isna().any(axis=1)
    # Weather can be interpolated for feature construction. Power is never filled,
    # because invented target values would contaminate training and validation.
    hourly[["wind_speed", "temperature"]] = hourly[["wind_speed", "temperature"]].interpolate(
        method="time", limit=6
    ).ffill().bfill()
    return hourly


def load_farm_data(files: list[Path]) -> FarmData:
    if len(files) < 2:
        raise FileNotFoundError("At least two turbine CSV files are required")
    raw_turbines = [_read_turbine(path) for path in files]
    start = min(t.index.min() for t in raw_turbines).floor("h")
    end = max(t.index.max() for t in raw_turbines).floor("h")
    index = pd.date_range(start, end, freq="1h", name="timestamp")
    turbines = [_complete_hourly(t, index) for t in raw_turbines]

    parts: list[pd.DataFrame] = []
    for number, turbine in enumerate(turbines, start=1):
        parts.append(turbine.rename(columns={
            "wind_speed": f"wind_speed_t{number}",
            "power": f"power_t{number}",
            "temperature": f"temperature_t{number}",
            "is_missing": f"is_missing_t{number}",
        }))
    hourly = pd.concat(parts, axis=1).sort_index()
    power_columns = [c for c in hourly if c.startswith("power_t")]
    wind_columns = [c for c in hourly if c.startswith("wind_speed_t")]
    temperature_columns = [c for c in hourly if c.startswith("temperature_t")]
    hourly["farm_power"] = hourly[power_columns].sum(axis=1, min_count=len(power_columns))
    hourly["wind_speed"] = hourly[wind_columns].mean(axis=1)
    hourly["temperature"] = hourly[temperature_columns].mean(axis=1)
    hourly["is_missing"] = hourly[[c for c in hourly if c.startswith("is_missing_t")]].any(axis=1)
    hourly = hourly.replace([np.inf, -np.inf], np.nan)
    return FarmData(hourly=hourly, turbines=raw_turbines, source_files=[str(p) for p in files])
