from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path

import pandas as pd

from .config import Settings
from .data import FarmData, load_farm_data
from .model import DirectMultiHorizonModel
from .weather import WeatherAgent


@dataclass
class ForecastRun:
    forecast: pd.DataFrame
    manifest: dict


class DataAgent:
    def __init__(self, settings: Settings):
        self.settings = settings

    def load(self) -> FarmData:
        return load_farm_data(self.settings.turbine_files)


class DataQualityAgent:
    def inspect(self, data: FarmData) -> dict:
        frame = data.hourly
        missing_power = int(frame["farm_power"].isna().sum())
        return {
            "status": "ok" if frame.index.is_monotonic_increasing and missing_power == 0 else "warning",
            "hourly_rows": int(len(frame)),
            "expected_frequency": "1h",
            "missing_power_rows": missing_power,
            "weather_interpolated_rows": int(frame["is_missing"].sum()),
            "time_span": [frame.index.min().isoformat(), frame.index.max().isoformat()],
        }


class ForecastAgent:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.model = DirectMultiHorizonModel(
            horizon_hours=settings.horizon_hours,
            alpha=settings.ridge_alpha,
        )

    def run(self, data: FarmData, cutoff: pd.Timestamp) -> ForecastRun:
        history = data.hourly.loc[data.hourly.index <= cutoff].copy()
        if len(history) < 100:
            raise ValueError(f"Only {len(history)} hourly rows available before {cutoff}")
        self.model.fit(history)
        weather_agent = WeatherAgent(self.settings.turbine_coordinates, self.settings.output_dir / "weather_cache")
        weather, weather_source = weather_agent.get_forecast(cutoff, self.settings.horizon_hours, history)
        forecast = self.model.forecast(history, weather)
        forecast = forecast.reset_index().rename(columns={"index": "timestamp"})
        quality = DataQualityAgent().inspect(data)
        manifest = {
            "created_at_utc": datetime.utcnow().isoformat() + "Z",
            "cutoff": cutoff.isoformat(),
            "horizon_hours": self.settings.horizon_hours,
            "weather_source": weather_source,
            "model": "direct multi-horizon ridge models with time-based lags and wind power curve",
            "no_lookahead": True,
            "coordinates": [list(x) for x in self.settings.turbine_coordinates],
            "training_rows": int(len(history)),
            "source_files": data.source_files,
            "data_quality": quality,
            "training_samples_by_horizon": self.model.sample_counts_,
            "stages": [
                {"stage": "data_quality", "problem_solved": "irregular hourly timestamps and silent gaps", "status": "completed"},
                {"stage": "weather_retrieval", "problem_solved": "forecast-time weather provenance", "status": weather_source},
                {"stage": "feature_engineering", "problem_solved": "row-based lags that were not real hours", "status": "completed"},
                {"stage": "forecasting", "problem_solved": "recursive error accumulation across 48 hours", "status": "completed"},
                {"stage": "audit", "problem_solved": "unverifiable forecast inputs and origins", "status": "completed"},
            ],
        }
        return ForecastRun(forecast=forecast, manifest=manifest)

    def replay(self, data: FarmData, start: pd.Timestamp, end: pd.Timestamp) -> ForecastRun:
        """Replay one forecast cycle per day without using future observations."""
        working = data.hourly.copy()
        day = start.floor("D")
        runs: list[pd.DataFrame] = []
        sources: list[str] = []
        while day <= end:
            cutoff = day - pd.Timedelta(hours=1)
            run = self.run(FarmData(working, data.turbines, data.source_files), cutoff)
            daily = run.forecast[run.forecast["timestamp"] < day + pd.Timedelta(days=1)].copy()
            daily["forecast_origin"] = cutoff
            runs.append(daily)
            sources.append(run.manifest["weather_source"])
            additions = daily.set_index("timestamp")[["forecast_farm_power", "wind_speed", "temperature"]]
            additions = additions.rename(columns={"forecast_farm_power": "farm_power"})
            working = pd.concat([working, additions]).sort_index()
            day += pd.Timedelta(days=1)
        forecast = pd.concat(runs, ignore_index=True)
        manifest = {
            "created_at_utc": datetime.utcnow().isoformat() + "Z",
            "replay_start": start.isoformat(),
            "replay_end": end.isoformat(),
            "horizon_hours": self.settings.horizon_hours,
            "weather_sources": sorted(set(sources)),
            "model": "daily sequential ridge autoregression",
            "no_lookahead": True,
            "coordinates": [list(x) for x in self.settings.turbine_coordinates],
            "source_files": data.source_files,
        }
        return ForecastRun(forecast=forecast, manifest=manifest)


def save_run(run: ForecastRun, output_dir: Path, prefix: str = "forecast") -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    forecast_path = output_dir / f"{prefix}.csv"
    manifest_path = output_dir / f"{prefix}_manifest.json"
    run.forecast.to_csv(forecast_path, index=False)
    manifest_path.write_text(json.dumps(run.manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return forecast_path, manifest_path
