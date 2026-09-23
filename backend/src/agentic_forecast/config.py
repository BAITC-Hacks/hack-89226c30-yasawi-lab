from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
import os


FIRST_ORIGIN = "2026-01-31T00:00:00+05:00"
LAST_ORIGIN = "2026-02-28T00:00:00+05:00"
CONFIGURATION_ID = "approved-replay-v1"
DEFAULT_FRONTEND_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
COORDINATES = {
    "turbine_1": (43.64513889, 78.53561111, "https://maps.app.goo.gl/iN6svMt69D5qRpFU9"),
    "turbine_2": (43.64319444, 78.53883333, "https://maps.app.goo.gl/8UQMwsYavY6nLvFY8"),
}


@dataclass(frozen=True)
class Settings:
    project_root: Path
    timezone: str = "Asia/Almaty"
    weather_base_url: str = "https://single-runs-api.open-meteo.com/v1/forecast"
    provider_timeout_seconds: float = 15.0
    provider_retries: int = 2
    frontend_origins: tuple[str, ...] = DEFAULT_FRONTEND_ORIGINS

    @property
    def data_dir(self) -> Path:
        return self.project_root / "data"

    @property
    def artifacts_dir(self) -> Path:
        return self.project_root / "backend" / "artifacts"

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def first_origin(self) -> datetime:
        return datetime.fromisoformat(FIRST_ORIGIN).astimezone(self.zone)


def frontend_origins_from_env() -> tuple[str, ...]:
    configured = os.getenv("FRONTEND_ORIGIN")
    if configured is None:
        return DEFAULT_FRONTEND_ORIGINS
    origins = []
    for value in configured.split(","):
        origin = value.strip().rstrip("/")
        parsed = urlsplit(origin)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username or parsed.password or parsed.path
                or parsed.query or parsed.fragment or "*" in origin):
            raise ValueError("FRONTEND_ORIGIN must contain comma-separated HTTP(S) origins without paths or wildcards")
        # Reading the port also rejects malformed or out-of-range port values.
        parsed.port
        if origin not in origins:
            origins.append(origin)
    return tuple(origins)


def default_settings(project_root: Path | None = None) -> Settings:
    root = (project_root or Path(__file__).resolve().parents[3]).resolve()
    return Settings(
        project_root=root,
        timezone=os.getenv("WIND_PROJECT_TIMEZONE", "Asia/Almaty"),
        weather_base_url=os.getenv("WIND_WEATHER_BASE_URL", "https://single-runs-api.open-meteo.com/v1/forecast"),
        provider_timeout_seconds=float(os.getenv("WIND_PROVIDER_TIMEOUT_SECONDS", "15")),
        frontend_origins=frontend_origins_from_env(),
    )
