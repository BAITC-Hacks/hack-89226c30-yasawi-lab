from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import tempfile
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import COORDINATES, CONFIGURATION_ID, FIRST_ORIGIN, LAST_ORIGIN, Settings
from .data import SourceQualityError, load_all, load_turbine
from .model import atomic_json, fit_or_load, predict
from .weather import WeatherBlocked, WeatherUnavailable, ordered_candidates, retrieve


STAGES = ["load_data", "validate_data", "aggregate_hourly", "train_or_load_models", "retrieve_weather",
          "validate_eligibility", "prepare_features", "forecast", "analyze", "decide_recalculation", "persist"]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def issue(code: str, message: str, severity: str = "error", details: dict | None = None) -> dict:
    result = {"code": code, "severity": severity, "message": message}
    if details is not None:
        result["details"] = details
    return result


def initial_result(run_id: str, origin: datetime, mode: str = "single", total_origins: int = 1) -> dict:
    return {"schema_version": "1.0", "run_id": run_id, "status": "queued", "mode": mode,
            "configuration_id": CONFIGURATION_ID, "is_mock": False,
            "origin_at": origin.isoformat(), "progress": {"completed_origins": 0, "blocked_origins": 0,
                                                    "failed_origins": 0, "total_origins": total_origins},
            "forecasts": [], "weather_snapshots": [], "model_manifests": [], "data_quality": {},
            "farm_aggregate": None,
            "farm_aggregate_reason": {"code": "AGGREGATION_RULE_UNAVAILABLE",
                                      "message": "No station aggregation rule or normalization denominator was supplied"},
            "evaluation": {"status": "unavailable", "scope": "February actual-based accuracy", "mae": None,
                           "rmse": None, "reason": "No February power actuals in supplied CSVs"},
            "agent": {"execution_mode": "bounded_deterministic_state_machine", "steps": [], "analysis": "",
                      "decisions": []}, "warnings": [], "errors": [], "turbine_outcomes": {}, "created_at_utc": now_utc()}


class RunStore:
    def __init__(self, settings: Settings):
        self.settings = settings

    def path(self, run_id: str) -> Path:
        return self.settings.artifacts_dir / "runs" / f"{run_id}.json"

    def save(self, result: dict) -> None:
        atomic_json(self.path(result["run_id"]), result)

    def load(self, run_id: str) -> dict | None:
        path = self.path(run_id)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def latest_for_origin(self, origin: datetime) -> dict | None:
        key = hashlib.sha256(origin.astimezone(timezone.utc).isoformat().encode()).hexdigest()[:20]
        path = self.settings.artifacts_dir / "runs" / "latest" / f"{key}.json"
        if not path.exists():
            return None
        pointer = json.loads(path.read_text(encoding="utf-8"))
        return self.load(pointer["run_id"])

    def remember_origin(self, result: dict) -> None:
        origin = datetime.fromisoformat(result["origin_at"])
        key = hashlib.sha256(origin.astimezone(timezone.utc).isoformat().encode()).hexdigest()[:20]
        atomic_json(self.settings.artifacts_dir / "runs" / "latest" / f"{key}.json",
                    {"run_id": result["run_id"], "origin_at": result["origin_at"]})


def _step(result: dict, name: str, status: str, reason: str, started: str | None = None,
          inputs: list[str] | None = None, outputs: list[str] | None = None) -> None:
    result["agent"]["steps"].append({"name": name, "status": status, "started_at_utc": started or now_utc(),
                                      "ended_at_utc": now_utc(), "reason": reason,
                                      "input_artifacts": inputs or [], "output_artifacts": outputs or []})


def _audit(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as target:
            writer = csv.writer(target)
            writer.writerow(["hour_local", "hour_utc", "wind_speed", "power", "temperature", "raw_sample_count",
                             "sample_count", "source_first_utc", "source_last_utc", "quality_flags"])
            for hour, row in data.hourly.iterrows():
                writer.writerow([hour.isoformat(), hour.tz_convert("UTC").isoformat(),
                                 *["" if not math.isfinite(row[k]) else row[k] for k in ("wind_speed", "power", "temperature")],
                                 row["raw_sample_count"], row["sample_count"],
                                 row["source_first_utc"], row["source_last_utc"], ";".join(row["quality_flags"])])
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _retrieve_first(settings: Settings, result: dict, turbine_id: str, origin: datetime):
    eligible, checks = ordered_candidates(settings, turbine_id, origin)
    result.setdefault("weather_candidates", {})[turbine_id] = checks
    if not eligible:
        raise WeatherBlocked("AVAILABILITY_UNVERIFIED", "No candidate clears the documented availability bound",
                             {"candidates": checks})
    last_error = None
    for index, run in enumerate(eligible):
        try:
            selection_reason = ("latest eligible cycle with full required coverage" if index == 0 else
                                "earlier eligible cycle after newer candidate lacked full required coverage")
            snapshot = retrieve(settings, turbine_id, origin, run, selection_reason=selection_reason)
            if snapshot.metadata["retries_used"] and not snapshot.metadata.get("reused_snapshot"):
                result["agent"]["decisions"].append({"action": "retry_provider", "turbine_id": turbine_id,
                    "run_at_utc": snapshot.metadata["run_at_utc"], "retries_used": snapshot.metadata["retries_used"],
                    "reason": "Transient weather provider error resolved within two retries"})
            return snapshot
        except WeatherBlocked as exc:
            last_error = exc
            for entry in checks:
                if entry["run_at_utc"] == run.isoformat().replace("+00:00", "Z"):
                    entry["retrieval_rejection"] = {"code": exc.code, "message": str(exc)}
            if index + 1 < len(eligible):
                result["agent"]["decisions"].append({"action": "select_older_eligible_run",
                    "turbine_id": turbine_id, "rejected_run_at_utc": run.isoformat().replace("+00:00", "Z"),
                    "reason": exc.code})
    if last_error:
        raise last_error
    raise WeatherBlocked("WEATHER_RUN_NOT_ELIGIBLE", "No eligible candidate weather run")


def run_first_origin(settings: Settings, run_id: str | None = None, origin: datetime | None = None,
                     preloaded: dict | None = None) -> dict:
    origin = origin or settings.first_origin
    result = initial_result(run_id or uuid.uuid4().hex, origin)
    store = RunStore(settings)
    previous = store.latest_for_origin(origin)
    result["input_fingerprints"] = {}
    store.save(result)
    result["status"] = "running"
    store.save(result)
    datasets = {}
    for turbine_id in COORDINATES:
        started = now_utc()
        number = turbine_id[-1]
        path = settings.data_dir / f"dataset_{number}.csv"
        try:
            data = preloaded[turbine_id] if preloaded is not None else load_turbine(path, turbine_id, settings.zone)
            datasets[turbine_id] = data
            result["data_quality"][turbine_id] = {**data.quality, "dataset_sha256": data.sha256,
                                                    "dataset_id": data.dataset_id}
            if data.quality["rejected_unlocalizable_rows"]:
                result["warnings"].append(issue("CSV_TIME_AMBIGUOUS",
                                                f"{turbine_id}: {data.quality['rejected_unlocalizable_rows']} ambiguous local timestamps excluded",
                                                "warning", {"turbine_id": turbine_id,
                                                            "examples": data.quality["rejected_unlocalizable_examples"]}))
            _step(result, "load_data", "completed", f"Loaded {data.raw_row_count} rows for {turbine_id}", started,
                  [str(path)])
            _step(result, "validate_data", "completed", "Exact source schema and values passed", inputs=[str(path)])
            audit = settings.artifacts_dir / "runs" / f"{result['run_id']}-{turbine_id}-hourly.csv"
            _audit(audit, data)
            result["data_quality"][turbine_id]["hourly_audit_path"] = str(audit)
            _step(result, "aggregate_hourly", "completed", f"{data.quality['complete_hours']} complete hours",
                  outputs=[str(audit)])
        except (SourceQualityError, FileNotFoundError, UnicodeError) as exc:
            detail = {"turbine_id": turbine_id, "path": str(path)}
            if isinstance(exc, SourceQualityError):
                detail.update(issue_count=len(exc.issues), examples=exc.issues[:10])
            result["errors"].append(issue("CSV_SOURCE_INVALID", str(exc), details=detail))
            result["turbine_outcomes"][turbine_id] = "blocked"
            _step(result, "load_data", "blocked", str(exc), started, [str(path)])
    store.save(result)
    models = {}
    for turbine_id, data in datasets.items():
        started = now_utc()
        try:
            fitted = fit_or_load(data, origin, settings.artifacts_dir)
            models[turbine_id] = fitted
            result["model_manifests"].append(fitted.manifest)
            _step(result, "train_or_load_models", "completed", f"{turbine_id} model {fitted.manifest['model_version']}",
                  started, [str(data.path)], [fitted.manifest["model_path"]])
        except ValueError as exc:
            result["errors"].append(issue("TRAINING_DATA_INSUFFICIENT", str(exc), details={"turbine_id": turbine_id}))
            result["turbine_outcomes"][turbine_id] = "blocked"
            _step(result, "train_or_load_models", "blocked", str(exc), started)
        except Exception as exc:
            result["errors"].append(issue("MODEL_RUNTIME_ERROR", f"Model fit failed for {turbine_id}", details={"turbine_id": turbine_id}))
            result["turbine_outcomes"][turbine_id] = "failed"
            _step(result, "train_or_load_models", "failed", str(exc), started)
            _log(settings, result["run_id"], exc)
    store.save(result)
    for turbine_id, fitted in models.items():
        started = now_utc()
        retrieved = False
        try:
            snapshot = _retrieve_first(settings, result, turbine_id, origin)
            retrieved = True
            result["weather_snapshots"].append(snapshot.metadata)
            _step(result, "retrieve_weather", "completed", f"Retrieved {snapshot.metadata['run_at_utc']}", started,
                  outputs=[snapshot.metadata["raw_path"]])
            _step(result, "validate_eligibility", "completed", "Historical availability and coverage proven")
            _step(result, "prepare_features", "completed", "Aligned 48 UTC valid hours to wind and temperature")
            fingerprint_inputs = {"origin_at": origin.isoformat(), "turbine_id": turbine_id,
                                  "dataset_sha256": datasets[turbine_id].sha256,
                                  "model_version": fitted.manifest["model_version"],
                                  "weather_snapshot_id": snapshot.metadata["weather_snapshot_id"],
                                  "requested_coordinate": snapshot.metadata.get("requested_coordinate", COORDINATES[turbine_id][:2])}
            fingerprint = hashlib.sha256(json.dumps(fingerprint_inputs, sort_keys=True).encode()).hexdigest()
            result["input_fingerprints"][turbine_id] = fingerprint
            old_rows = ([row for row in previous.get("forecasts", []) if row["turbine_id"] == turbine_id]
                        if previous else [])
            old_rows.sort(key=lambda row: row["lead_hours"])
            same_input = bool(previous and previous.get("input_fingerprints", {}).get(turbine_id) == fingerprint
                              and len(old_rows) == 48)
            try:
                predicted = ([row["power_normalized"] for row in old_rows] if same_input else
                             predict(fitted.model, snapshot.wind, snapshot.temperature))
            except ValueError as exc:
                raise WeatherBlocked("FORECAST_OUTPUT_INVALID", str(exc),
                                     {"model_version": fitted.manifest["model_version"]}) from exc
            changed_input = bool(previous and previous.get("input_fingerprints", {}).get(turbine_id)
                                 and not same_input)
            if same_input:
                result["agent"]["decisions"].append({"action": "reuse_unchanged_calculation", "turbine_id": turbine_id,
                    "previous_run_id": previous["run_id"], "input_fingerprint": fingerprint})
            elif changed_input:
                result["agent"]["decisions"].append({"action": "recalculate", "turbine_id": turbine_id,
                    "previous_run_id": previous["run_id"], "input_fingerprint": fingerprint,
                    "reason": "Effective calculation dependency changed"})
            _step(result, "forecast", "completed", f"{'Reused' if same_input else 'Predicted'} 48 hours for {turbine_id}")
            for h, power in enumerate(predicted):
                valid_start = origin + timedelta(hours=h)
                valid_end = valid_start + timedelta(hours=1)
                result["forecasts"].append({"dataset_id": f"dataset_{turbine_id[-1]}.csv", "turbine_id": turbine_id,
                                            "origin_at": origin.isoformat(), "valid_start": valid_start.isoformat(),
                                            "valid_end": valid_end.isoformat(), "lead_hours": h + 1,
                                            "power_normalized": power, "actual_power_normalized": None,
                                            "weather_snapshot_id": snapshot.metadata["weather_snapshot_id"],
                                            "model_version": fitted.manifest["model_version"],
                                            "in_test_period": valid_start.month == 2 and valid_start.year == 2026,
                                            "previous_run_id": previous["run_id"] if changed_input and len(old_rows) == 48 else None,
                                            "revision_delta": power - old_rows[h]["power_normalized"] if changed_input and len(old_rows) == 48 else None,
                                            "quality_flags": []})
            result["turbine_outcomes"][turbine_id] = "completed"
        except WeatherBlocked as exc:
            snapshot_id = exc.details.get("weather_snapshot_id")
            if snapshot_id:
                manifest_path = settings.artifacts_dir / "weather" / f"{snapshot_id}.manifest.json"
                if manifest_path.exists():
                    result["weather_snapshots"].append(json.loads(manifest_path.read_text(encoding="utf-8")))
            result["errors"].append(issue(exc.code, str(exc), details={"turbine_id": turbine_id, **exc.details}))
            result["turbine_outcomes"][turbine_id] = "blocked"
            if not retrieved:
                _step(result, "retrieve_weather", "blocked", f"No usable archived weather for {turbine_id}", started)
                _step(result, "validate_eligibility", "blocked", str(exc))
            else:
                _step(result, "forecast", "blocked", str(exc), started)
        except WeatherUnavailable as exc:
            result["agent"]["decisions"].append({"action": "retry_provider", "turbine_id": turbine_id,
                "retries_used": settings.provider_retries, "reason": "Provider remained unavailable after bounded retries"})
            result["errors"].append(issue("WEATHER_PROVIDER_UNAVAILABLE", str(exc), details={"turbine_id": turbine_id}))
            result["turbine_outcomes"][turbine_id] = "failed"
            _step(result, "retrieve_weather", "failed", str(exc), started)
        except Exception as exc:
            result["errors"].append(issue("MODEL_RUNTIME_ERROR", f"Forecast failed for {turbine_id}", details={"turbine_id": turbine_id}))
            result["turbine_outcomes"][turbine_id] = "failed"
            _step(result, "forecast", "failed", str(exc), started)
            _log(settings, result["run_id"], exc)
        store.save(result)
    present_stages = {item["name"] for item in result["agent"]["steps"]}
    for stage in STAGES[1:8]:
        if stage not in present_stages:
            _step(result, stage, "skipped", "A required earlier stage was blocked or failed")
    powers = [row["power_normalized"] for row in result["forecasts"]]
    result["summary"] = {"forecast_rows": len(powers), "per_turbine": {
        tid: {"mean": sum(vals) / len(vals), "min": min(vals), "max": max(vals), "coverage_count": len(vals)}
        for tid in COORDINATES if (vals := [r["power_normalized"] for r in result["forecasts"] if r["turbine_id"] == tid])}}
    _step(result, "analyze", "completed", "Computed only per-turbine normalized summaries and coverage")
    result["agent"]["analysis"] = "Forecast evidence and turbine outcomes reviewed; no unproven weather used."
    action = "complete" if len(powers) == 96 else ("fail" if all(x == "failed" for x in result["turbine_outcomes"].values()) else "block")
    result["agent"]["decisions"].append({"action": action,
                                           "reason": "Weather availability or input is unverified" if action == "block" else ("Runtime/provider fault" if action == "fail" else "Validated forecast rows saved"),
                                           "recalculation_count": 0})
    recalculated = any(item["action"] == "recalculate" for item in result["agent"]["decisions"])
    result["agent"]["decisions"][-1]["recalculation_count"] = int(recalculated)
    _step(result, "decide_recalculation", "completed",
          f"Changed effective input {'recalculated' if recalculated else 'not detected'}; recalculation count {int(recalculated)} of 1")
    outcomes = list(result["turbine_outcomes"].values())
    if outcomes and all(x == "completed" for x in outcomes):
        result["status"] = "completed"
        result["progress"]["completed_origins"] = 1
    elif "completed" in outcomes:
        result["status"] = "partial"
        result["progress"]["completed_origins"] = 1
    elif "blocked" in outcomes:
        result["status"] = "blocked"
        result["progress"]["blocked_origins"] = 1
    else:
        result["status"] = "failed"
        result["progress"]["failed_origins"] = 1
    if any(outcome != "completed" for outcome in outcomes):
        result["farm_aggregate_reason"] = {"code": "INCOMPLETE_TURBINE_PREDICTIONS",
            "message": "At least one turbine lacks a validated 48-hour prediction; no station aggregation rule is supplied"}
    _step(result, "persist", "completed", "Atomic run JSON and hourly audit saved", outputs=[str(store.path(result["run_id"]))])
    result["ended_at_utc"] = now_utc()
    store.save(result)
    if result["status"] in ("completed", "partial") and result["forecasts"]:
        store.remember_origin(result)
    return result


def run_replay(settings: Settings, run_id: str | None = None, from_origin: datetime | None = None,
               through_origin: datetime | None = None) -> dict:
    first = from_origin or datetime.fromisoformat(FIRST_ORIGIN).astimezone(settings.zone)
    last = through_origin or datetime.fromisoformat(LAST_ORIGIN).astimezone(settings.zone)
    origins = [first + timedelta(days=day) for day in range((last.date() - first.date()).days + 1)]
    result = initial_result(run_id or uuid.uuid4().hex, first, "replay", len(origins))
    result["from_origin"] = first.isoformat()
    result["through_origin"] = last.isoformat()
    result["origins"] = []
    result["summary"] = {"total_origins": len(origins), "success": 0, "blocked": 0, "failed": 0,
                         "with_farm_aggregate": 0, "without_farm_aggregate": 0}
    store = RunStore(settings)
    store.save(result)
    result["status"] = "running"
    store.save(result)
    try:
        preloaded = load_all(settings.data_dir, settings.zone)
    except (SourceQualityError, FileNotFoundError, UnicodeError):
        preloaded = None  # Per-origin validation records the affected turbine and exact source error.
    for origin in origins:
        started = now_utc()
        try:
            child = run_first_origin(settings, origin=origin, preloaded=preloaded)
        except Exception as exc:
            _log(settings, result["run_id"], exc)
            child = initial_result(uuid.uuid4().hex, origin)
            child["status"] = "failed"
            child["progress"]["failed_origins"] = 1
            child["errors"].append(issue("RUN_RUNTIME_ERROR", "Unexpected origin fault; inspect local logs",
                                         details={"origin_at": origin.isoformat()}))
            child["ended_at_utc"] = now_utc()
            store.save(child)
        outcomes = child.get("turbine_outcomes", {})
        if child["status"] == "completed":
            category = "success"
            result["progress"]["completed_origins"] += 1
        elif child["status"] == "failed" or (child["status"] == "partial" and "blocked" not in outcomes.values()):
            category = "failed"
            result["progress"]["failed_origins"] += 1
        else:
            category = "blocked"
            result["progress"]["blocked_origins"] += 1
        result["summary"][category] += 1
        has_aggregate = child.get("farm_aggregate") is not None
        result["summary"]["with_farm_aggregate" if has_aggregate else "without_farm_aggregate"] += 1
        result["origins"].append({"origin_at": origin.isoformat(), "run_id": child["run_id"],
            "status": child["status"], "summary_category": category, "turbine_outcomes": outcomes,
            "forecast_rows": len(child.get("forecasts", [])), "selected_weather": [
                {"turbine_id": item.get("turbine_id"), "run_at_utc": item["run_at_utc"],
                 "availability_method": item.get("availability_method"),
                 "available_by_utc": item.get("available_by_utc"),
                 "weather_snapshot_id": item["weather_snapshot_id"]}
                for item in child.get("weather_snapshots", []) if item.get("eligibility") == "eligible"],
            "errors": child.get("errors", []), "farm_aggregate": child.get("farm_aggregate"),
            "farm_aggregate_reason": child.get("farm_aggregate_reason"),
            "input_fingerprints": child.get("input_fingerprints", {})})
        result["forecasts"].extend(child.get("forecasts", []))
        result["weather_snapshots"].extend(child.get("weather_snapshots", []))
        result["model_manifests"].extend(child.get("model_manifests", []))
        if not result["data_quality"]:
            result["data_quality"] = child.get("data_quality", {})
        result["errors"].extend(child.get("errors", []))
        _step(result, "run_origin", child["status"], f"{origin.isoformat()}: {child['status']}", started,
              outputs=[str(store.path(child["run_id"]))])
        store.save(result)
    success, blocked, failed = (result["summary"][key] for key in ("success", "blocked", "failed"))
    result["status"] = ("completed" if success == len(origins) else
                        "partial" if success or (blocked and failed) else
                        "blocked" if blocked else "failed")
    if blocked or failed:
        result["farm_aggregate_reason"] = {"code": "INCOMPLETE_TURBINE_PREDICTIONS",
            "message": "At least one origin lacks validated turbine predictions; no station aggregation rule is supplied"}
    result["agent"]["analysis"] = "Sequential origin outcomes and provenance are recorded in origins."
    result["agent"]["decisions"].append({"action": "complete_replay", "reason": "All requested origins visited",
                                          "visited_origins": len(result["origins"])})
    _step(result, "persist", "completed", "Atomic replay and per-origin results saved",
          outputs=[str(store.path(result["run_id"]))])
    result["ended_at_utc"] = now_utc()
    store.save(result)
    return result


def _log(settings: Settings, run_id: str, exc: Exception) -> None:
    path = settings.artifacts_dir / "logs" / f"{run_id}.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as target:
        target.write(traceback.format_exc() + "\n")
