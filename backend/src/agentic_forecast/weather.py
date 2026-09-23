from __future__ import annotations

import hashlib
import json
import math
import ssl
import time
import os
import tempfile
import urllib.parse
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import certifi

from .config import COORDINATES, Settings
from .model import atomic_json


DOCUMENTATION_URL = "https://open-meteo.com/en/docs/single-runs-api"
DISSEMINATION_URL = "https://confluence.ecmwf.int/pages/viewpage.action?pageId=540563877"
MODEL_ID = "ecmwf_ifs"
VARIABLES = ["wind_speed_100m", "temperature_2m"]
# Latest delivery of the needed 0–90 h atmospheric steps; 00/12 UTC also
# include ECMWF's later post-processed weather-parameter schedule.
SCHEDULE_CLOCK_UTC = {0: (6, 55), 6: (12, 12), 12: (18, 55), 18: (0, 12)}
SAFETY_MARGIN_MINUTES = 10
PROVIDER_DELAY_MINUTES = 360


class WeatherBlocked(ValueError):
    def __init__(self, code: str, message: str, details: dict | None = None):
        self.code, self.details = code, details or {}
        super().__init__(message)


class WeatherUnavailable(RuntimeError):
    pass


@dataclass
class WeatherSnapshot:
    metadata: dict
    wind: list[float]
    temperature: list[float]


def candidate_runs(origin: datetime, count: int = 8) -> list[datetime]:
    cursor = origin.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    cursor -= timedelta(hours=cursor.hour % 6)
    return [cursor - timedelta(hours=6 * i) for i in range(count)]


def ordered_candidates(settings: Settings, turbine_id: str, origin: datetime) -> tuple[list[datetime], list[dict]]:
    checks = []
    eligible = []
    for run in candidate_runs(origin):
        verdict, reason, available = availability_verdict(run, origin, _evidence(settings, turbine_id, run))
        checks.append({"run_at_utc": run.isoformat().replace("+00:00", "Z"), "availability_status": verdict,
                       "reason": reason, "available_by_utc": available.isoformat().replace("+00:00", "Z") if available else None})
        if verdict == "eligible":
            eligible.append(run)
    return eligible, checks


def _evidence(settings: Settings, turbine_id: str, run: datetime) -> dict | None:
    path = settings.artifacts_dir / "weather" / "availability_evidence.json"
    if path.exists():
        entries = json.loads(path.read_text(encoding="utf-8"))
        key = f"{turbine_id}/{run:%Y-%m-%dT%H:%MZ}"
        item = entries.get(key)
        if item and all(item.get(k) for k in ("available_by_utc", "evidence_type", "source_url", "recorded_at_utc")):
            return item
    if run.tzinfo is None or run.hour not in SCHEDULE_CLOCK_UTC or run.minute != 0:
        return None
    if not datetime(2025, 7, 2, tzinfo=timezone.utc) <= run < datetime(2026, 5, 12, tzinfo=timezone.utc):
        return None
    delivery_hour, delivery_minute = SCHEDULE_CLOCK_UTC[run.hour]
    delivery = run.replace(hour=delivery_hour, minute=delivery_minute)
    if delivery <= run:
        delivery += timedelta(days=1)
    processing_bound = run + timedelta(minutes=PROVIDER_DELAY_MINUTES)
    base_bound = max(delivery, processing_bound)
    available_bound = base_bound + timedelta(minutes=SAFETY_MARGIN_MINUTES)
    return {"evidence_type": "conservative_schedule_delay_bound",
            "availability_method": "schedule_bound", "model": "ECMWF IFS HRES 9km",
            "provider": "Open-Meteo Single Runs", "cycle_time_utc": run.isoformat().replace("+00:00", "Z"),
            "available_by_utc": available_bound.isoformat().replace("+00:00", "Z"),
            "source_urls": [DISSEMINATION_URL, DOCUMENTATION_URL],
            "schedule_source": DISSEMINATION_URL, "provider_delay_source": DOCUMENTATION_URL,
            "ecmwf_schedule_last_updated": "2025-07-02",
            "nominal_release_utc": delivery.isoformat().replace("+00:00", "Z"),
            "delivery_bound_utc": delivery.isoformat().replace("+00:00", "Z"),
            "documented_provider_delay_minutes": PROVIDER_DELAY_MINUTES,
            "open_meteo_processing_bound_utc": processing_bound.isoformat().replace("+00:00", "Z"),
            "safety_margin_minutes": SAFETY_MARGIN_MINUTES,
            "interpretation": "Conservative replay eligibility bound, not an observed Open-Meteo publication timestamp"}


def availability_verdict(run: datetime, origin: datetime, evidence: dict | None) -> tuple[str, str, datetime | None]:
    if evidence is None:
        return "unverified", "AVAILABILITY_UNVERIFIED", None
    try:
        available = datetime.fromisoformat(evidence["available_by_utc"].replace("Z", "+00:00"))
    except (ValueError, KeyError):
        return "unverified", "AVAILABILITY_UNVERIFIED", None
    if available.tzinfo is None:
        return "unverified", "AVAILABILITY_UNVERIFIED", None
    if evidence.get("evidence_type") == "conservative_schedule_delay_bound":
        try:
            nominal = datetime.fromisoformat(evidence["nominal_release_utc"].replace("Z", "+00:00"))
            cycle = datetime.fromisoformat(evidence["cycle_time_utc"].replace("Z", "+00:00"))
            delay = evidence["documented_provider_delay_minutes"]
            margin = evidence["safety_margin_minutes"]
            if (nominal.tzinfo is None or cycle != run or
                    evidence["schedule_source"] != DISSEMINATION_URL or
                    evidence["provider_delay_source"] != DOCUMENTATION_URL or
                    delay != PROVIDER_DELAY_MINUTES or margin != SAFETY_MARGIN_MINUTES or
                    max(nominal, cycle + timedelta(minutes=delay)) + timedelta(minutes=margin) != available):
                return "unverified", "AVAILABILITY_UNVERIFIED", None
        except (KeyError, ValueError, TypeError, OverflowError):
            return "unverified", "AVAILABILITY_UNVERIFIED", None
    else:
        try:
            recorded = datetime.fromisoformat(evidence["recorded_at_utc"].replace("Z", "+00:00"))
        except (ValueError, KeyError):
            return "unverified", "AVAILABILITY_UNVERIFIED", None
        if recorded.tzinfo is None or recorded > origin:
            return "unverified", "AVAILABILITY_UNVERIFIED", None
    if run <= available <= origin.astimezone(timezone.utc):
        return "eligible", "ELIGIBLE", available
    return "ineligible", "WEATHER_RUN_NOT_ELIGIBLE", available


def validate_hourly(payload: dict, origin: datetime) -> tuple[list[float], list[float], list[str], dict]:
    units = payload.get("hourly_units") or {}
    if units.get("wind_speed_100m") != "m/s" or units.get("temperature_2m") != "°C":
        raise WeatherBlocked("WEATHER_UNITS_INVALID", "Provider weather units differ from m/s and °C", {"units": units})
    if payload.get("utc_offset_seconds") != 0 or payload.get("timezone") not in ("GMT", "UTC"):
        raise WeatherBlocked("WEATHER_TIMEZONE_INVALID", "Provider response is not UTC")
    if payload.get("models") not in (None, MODEL_ID):
        raise WeatherBlocked("WEATHER_MODEL_INVALID", "Provider returned another model")
    hourly = payload.get("hourly") or {}
    times, wind, temperature = (hourly.get("time") or []), (hourly.get("wind_speed_100m") or []), (hourly.get("temperature_2m") or [])
    if not (len(times) == len(wind) == len(temperature)):
        raise WeatherBlocked("WEATHER_COVERAGE_INCOMPLETE", "Weather arrays have different lengths")
    index = {}
    all_times = []
    for i, raw in enumerate(times):
        try:
            valid = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if valid.tzinfo is None:
                valid = valid.replace(tzinfo=timezone.utc)
            valid = valid.astimezone(timezone.utc)
        except ValueError:
            raise WeatherBlocked("WEATHER_TIMESTAMP_INVALID", f"Invalid weather timestamp: {raw}")
        if valid in index:
            raise WeatherBlocked("WEATHER_DUPLICATE_HOUR", f"Duplicate weather timestamp: {raw}")
        index[valid] = i
        all_times.append(valid.isoformat().replace("+00:00", "Z"))
    selected_wind, selected_temperature, selected_times = [], [], []
    for h in range(48):
        valid = origin.astimezone(timezone.utc) + timedelta(hours=h)
        if valid not in index:
            raise WeatherBlocked("WEATHER_COVERAGE_INCOMPLETE", f"Missing weather hour: {valid.isoformat()}")
        i = index[valid]
        try:
            w, t = float(wind[i]), float(temperature[i])
        except (TypeError, ValueError):
            raise WeatherBlocked("WEATHER_VALUE_INVALID", f"Null or invalid weather at {valid.isoformat()}")
        if not math.isfinite(w) or not math.isfinite(t) or w < 0:
            raise WeatherBlocked("WEATHER_VALUE_INVALID", f"Invalid weather at {valid.isoformat()}")
        selected_wind.append(w)
        selected_temperature.append(t)
        selected_times.append(valid.isoformat().replace("+00:00", "Z"))
    return selected_wind, selected_temperature, selected_times, {"all_valid_times_utc": all_times, "coverage_count": 48}


def _fetch(url: str, timeout: float, retries: int) -> tuple[bytes, int, int]:
    last_error = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=timeout, context=ssl.create_default_context(cafile=certifi.where())) as response:
                return response.read(), response.status, attempt
        except urllib.error.HTTPError as exc:
            if exc.code not in (408, 425, 429, 500, 502, 503, 504):
                raise WeatherBlocked("WEATHER_RUN_NOT_ELIGIBLE", f"Provider rejected candidate run (HTTP {exc.code})") from exc
            last_error = exc
            if attempt < retries:
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                delay = float(retry_after) if retry_after and retry_after.isdecimal() else 2 ** attempt
                time.sleep(min(delay, 2))
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(min(2 ** attempt, 2))
    raise WeatherUnavailable(f"Open-Meteo request failed after {retries + 1} attempts: {last_error}")


def _selected_path(settings: Settings, turbine_id: str, origin: datetime, url: str) -> Path:
    key = hashlib.sha256(f"{turbine_id}/{origin.astimezone(timezone.utc).isoformat()}/{url}".encode()).hexdigest()
    return settings.artifacts_dir / "weather" / "selected" / f"{key}.json"


def _frozen_snapshot(path: Path, settings: Settings, origin: datetime) -> WeatherSnapshot | None:
    if not path.exists():
        return None
    try:
        pointer = json.loads(path.read_text(encoding="utf-8"))
        snapshot_id = pointer["weather_snapshot_id"]
        folder = settings.artifacts_dir / "weather"
        metadata = json.loads((folder / f"{snapshot_id}.manifest.json").read_text(encoding="utf-8"))
        raw = (folder / f"{snapshot_id}.json").read_bytes()
        if metadata["weather_snapshot_id"] != snapshot_id or hashlib.sha256(raw).hexdigest() != metadata["raw_sha256"]:
            raise ValueError("frozen snapshot digest or identity mismatch")
        run = datetime.fromisoformat(metadata["run_at_utc"].replace("Z", "+00:00"))
        verdict, _, _ = availability_verdict(run, origin, metadata["availability_evidence"])
        if verdict != "eligible":
            raise ValueError("frozen snapshot availability is not eligible")
        wind, temperature, selected, _ = validate_hourly(json.loads(raw), origin)
        if selected != metadata["selected_valid_times_utc"]:
            raise ValueError("frozen snapshot coverage mismatch")
        return WeatherSnapshot({**metadata, "reused_snapshot": True}, wind, temperature)
    except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError, WeatherBlocked) as exc:
        raise WeatherUnavailable(f"Frozen historical weather snapshot is corrupt: {exc}") from exc


def retrieve(settings: Settings, turbine_id: str, origin: datetime, run: datetime,
             fetcher=None, selection_reason: str = "latest eligible cycle with full required coverage") -> WeatherSnapshot:
    latitude, longitude, coordinate_source = COORDINATES[turbine_id]
    params = {"latitude": latitude, "longitude": longitude, "run": run.strftime("%Y-%m-%dT%H:%M"),
              "models": MODEL_ID, "hourly": ",".join(VARIABLES), "timezone": "UTC",
              "wind_speed_unit": "ms", "forecast_hours": 96}
    url = f"{settings.weather_base_url}?{urllib.parse.urlencode(params)}"
    selected_path = _selected_path(settings, turbine_id, origin, url)
    frozen = _frozen_snapshot(selected_path, settings, origin)
    if frozen is not None:
        return frozen
    raw, status, retries_used = (fetcher or _fetch)(url, settings.provider_timeout_seconds, settings.provider_retries)
    retrieved_at = datetime.now(timezone.utc).isoformat()
    digest = hashlib.sha256(raw).hexdigest()
    evidence = _evidence(settings, turbine_id, run)
    evidence_digest = hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()
    snapshot_id = hashlib.sha256(f"{turbine_id}/{origin.astimezone(timezone.utc).isoformat()}/{url}/{digest}/{evidence_digest}".encode()).hexdigest()[:20]
    raw_path = settings.artifacts_dir / "weather" / f"{snapshot_id}.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    if not raw_path.exists():
        fd, name = tempfile.mkstemp(dir=raw_path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as target:
                target.write(raw)
            os.replace(name, raw_path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
    verdict, reason, available = availability_verdict(run, origin, evidence)
    metadata = {"weather_snapshot_id": snapshot_id, "turbine_id": turbine_id,
                "provider": "Open-Meteo", "model": "ECMWF IFS HRES 9km",
                "provider_model_id": MODEL_ID, "request_url": url, "request_parameters": params,
                "http_status": status, "retrieved_at_utc": retrieved_at, "source_reference": DOCUMENTATION_URL,
                "coordinate_source": coordinate_source, "requested_coordinate": {"latitude": latitude, "longitude": longitude},
                "run_at_utc": run.isoformat().replace("+00:00", "Z"),
                "availability_method": "schedule_bound" if evidence and evidence.get("evidence_type") == "conservative_schedule_delay_bound" else "exact_timestamp" if evidence else "unverified",
                "available_by_utc": available.isoformat().replace("+00:00", "Z") if available else None,
                "availability_evidence": evidence, "eligibility": verdict, "eligibility_reason": reason,
                "selection_reason": selection_reason,
                "origin_utc": origin.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                "variables": VARIABLES, "variable_heights_m": {"wind_speed_100m": 100, "temperature_2m": 2},
                "raw_sha256": digest, "raw_path": str(raw_path), "retries_used": retries_used}
    try:
        payload = json.loads(raw)
        metadata.update(provider_grid_coordinate={"latitude": payload.get("latitude"), "longitude": payload.get("longitude"),
                                                  "elevation": payload.get("elevation")},
                        provider_timezone=payload.get("timezone"), provider_utc_offset_seconds=payload.get("utc_offset_seconds"),
                        hourly_units=payload.get("hourly_units"))
        wind, temperature, selected, checks = validate_hourly(payload, origin)
        metadata.update(selected_valid_times_utc=selected,
                        coverage_start_utc=selected[0],
                        coverage_end_utc=(datetime.fromisoformat(selected[-1].replace("Z", "+00:00")) + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
                        **checks)
    except (json.JSONDecodeError, WeatherBlocked) as exc:
        metadata.update(coverage_count=0, validation_error=str(exc))
        manifest_path = settings.artifacts_dir / "weather" / f"{snapshot_id}.manifest.json"
        if not manifest_path.exists():
            atomic_json(manifest_path, metadata)
        if isinstance(exc, WeatherBlocked):
            raise
        raise WeatherBlocked("WEATHER_RESPONSE_INVALID", "Provider response is not JSON") from exc
    manifest_path = settings.artifacts_dir / "weather" / f"{snapshot_id}.manifest.json"
    if manifest_path.exists():
        metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        atomic_json(manifest_path, metadata)
    if verdict != "eligible":
        raise WeatherBlocked(reason, "Weather run is not eligible at the forecast origin",
                             {"weather_snapshot_id": snapshot_id, "run_at_utc": metadata["run_at_utc"],
                              "availability_evidence": evidence})
    if not selected_path.exists():
        atomic_json(selected_path, {"weather_snapshot_id": snapshot_id, "request_url": url,
                                    "origin_utc": origin.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")})
    return WeatherSnapshot(metadata, wind, temperature)
