from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class WeatherAgent:
    coordinates: tuple[tuple[float, float], ...]
    cache_dir: Path
    timeout_seconds: int = 30

    def _request(self, base_url: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        lat = ",".join(str(x[0]) for x in self.coordinates)
        lon = ",".join(str(x[1]) for x in self.coordinates)
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start.date().isoformat(),
            "end_date": end.date().isoformat(),
            "hourly": "wind_speed_10m,temperature_2m",
            "timezone": "auto",
        }
        url = f"{base_url}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        series = payload if isinstance(payload, list) else [payload]
        frames = []
        for item in series:
            hourly = item["hourly"]
            frames.append(pd.DataFrame({
                "timestamp": pd.to_datetime(hourly["time"]),
                "wind_speed": hourly["wind_speed_10m"],
                "temperature": hourly["temperature_2m"],
            }).set_index("timestamp"))
        result = pd.concat(frames).groupby(level=0).mean().sort_index()
        return result.loc[(result.index >= start.floor("h")) & (result.index <= end.floor("h"))]

    def _fallback(self, history: pd.DataFrame, index: pd.DatetimeIndex) -> pd.DataFrame:
        source = history[["wind_speed", "temperature"]].copy()
        values = []
        for timestamp in index:
            candidates = source[
                (source.index.month == timestamp.month)
                & (source.index.hour == timestamp.hour)
                & (source.index.dayofweek == timestamp.dayofweek)
            ]
            if candidates.empty:
                candidates = source[
                    (source.index.month == timestamp.month)
                    & (source.index.hour == timestamp.hour)
                ]
            if candidates.empty:
                candidates = source.tail(24)
            values.append(candidates.mean(numeric_only=True))
        return pd.DataFrame(values, index=index).ffill().bfill()

    def get_forecast(self, cutoff: pd.Timestamp, horizon_hours: int, history: pd.DataFrame) -> tuple[pd.DataFrame, str]:
        start = cutoff + pd.Timedelta(hours=1)
        end = cutoff + pd.Timedelta(hours=horizon_hours)
        cache_path = self.cache_dir / f"weather_{start:%Y%m%d%H}_{end:%Y%m%d%H}.csv"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if cache_path.exists():
            return pd.read_csv(cache_path, parse_dates=["timestamp"]).set_index("timestamp"), "cache"
        try:
            # This archive contains weather forecasts rather than later observations,
            # which preserves the challenge's no-look-ahead requirement during replay.
            frame = self._request("https://historical-forecast-api.open-meteo.com/v1/forecast", start, end)
            frame = frame.reindex(pd.date_range(start, end, freq="1h", name="timestamp")).interpolate().ffill().bfill()
            frame.reset_index().to_csv(cache_path, index=False)
            return frame, "open-meteo-historical-forecast"
        except Exception as exc:  # noqa: BLE001 - offline/replay fallback is intentional
            frame = self._fallback(history, pd.date_range(start, end, freq="1h", name="timestamp"))
            frame.attrs["weather_warning"] = str(exc)
            return frame, "seasonal-persistence-fallback"
