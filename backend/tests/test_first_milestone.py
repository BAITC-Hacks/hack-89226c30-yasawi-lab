from __future__ import annotations

import csv
import hashlib
import json
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from agentic_forecast import api
from agentic_forecast import agents, weather
from agentic_forecast.agents import RunStore, initial_result, run_first_origin, run_replay
from agentic_forecast.config import Settings
from agentic_forecast.data import HEADERS, SourceQualityError, load_turbine
from agentic_forecast.model import fit_or_load
from agentic_forecast.weather import WeatherBlocked, WeatherSnapshot, availability_verdict, ordered_candidates, retrieve, validate_hourly


ZONE = ZoneInfo("Asia/Almaty")
ORIGIN = datetime.fromisoformat("2026-01-31T00:00:00+05:00")


def make_csv_portable(path: Path, **kwargs) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    hours = kwargs.get("hours", 24 * 20)
    missing_hour = kwargs.get("missing_hour")
    incomplete_hour = kwargs.get("incomplete_hour")
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(HEADERS[:-1] + ["wrong"] if kwargs.get("bad_header") else HEADERS)
        row_id = 0
        for h in range(hours):
            if h == missing_hour:
                continue
            for slot in range(6):
                if h == incomplete_hour and slot == 3:
                    continue
                row_id += 1
                at = ORIGIN - timedelta(hours=hours) + timedelta(hours=h, minutes=10 * slot)
                stamp = f"{at:%Y-%m-%d} {at.hour}:{at:%M:%S}"
                wind = 4 + h % 12
                writer.writerow([row_id, stamp, wind, 0 if h == 0 else min(wind / 20, 1), 12])


def test_strict_csv_hash_hourly_quality_and_zero(tmp_path: Path):
    path = tmp_path / "dataset_1.csv"
    make_csv_portable(path, hours=120, missing_hour=3, incomplete_hour=4)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    data = load_turbine(path, "turbine_1", ZONE)
    assert data.sha256 == before == hashlib.sha256(path.read_bytes()).hexdigest()
    assert data.quality["missing_hours"] == 1
    assert data.quality["incomplete_hours"] == 1
    assert data.quality["complete_hours"] == 118
    assert data.hourly.iloc[0]["power"] == 0
    assert data.hourly.iloc[3]["quality_flags"] == ["MISSING_HOUR"]
    assert data.hourly.iloc[4]["sample_count"] == 5
    assert data.hourly.iloc[4]["quality_flags"] == ["INCOMPLETE_HOUR"]
    assert data.hourly.iloc[4]["wind_speed"] == 8
    make_csv_portable(path, hours=1, bad_header=True)
    with pytest.raises(SourceQualityError):
        load_turbine(path, "turbine_1", ZONE)


def test_cutoff_and_timezone(tmp_path: Path):
    path = tmp_path / "dataset_1.csv"
    make_csv_portable(path)
    with path.open("a", encoding="utf-8") as target:
        target.write("99999,2026-01-31 0:00:00,100,1,20\n")
    data = load_turbine(path, "turbine_1", ZONE)
    fitted = fit_or_load(data, ORIGIN, Settings(tmp_path).artifacts_dir)
    assert fitted.manifest["identity"]["training_cutoff"] == ORIGIN.isoformat()
    assert fitted.manifest["last_training_hour"] == "2026-01-30T23:00:00+05:00"
    assert fitted.manifest["training_rows"] == 480
    assert ORIGIN.astimezone(timezone.utc).isoformat() == "2026-01-30T19:00:00+00:00"
    assert fitted.manifest["evaluation"]["holdout_rows"] == 336


def test_weather_availability_and_48_hour_alignment():
    run = datetime.fromisoformat("2026-01-30T12:00:00+00:00")
    assert availability_verdict(run, ORIGIN, None)[0] == "unverified"
    evidence = {"available_by_utc": "2026-01-30T17:00:00Z", "recorded_at_utc": "2026-01-30T18:00:00Z",
                "evidence_type": "publication_log", "source_url": "https://example.test/log"}
    assert availability_verdict(run, ORIGIN, evidence)[0] == "eligible"
    evidence["available_by_utc"] = "2026-01-30T20:00:00Z"
    assert availability_verdict(run, ORIGIN, evidence)[0] == "ineligible"
    start = ORIGIN.astimezone(timezone.utc)
    times = [(start + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(48)]
    payload = {"timezone": "GMT", "utc_offset_seconds": 0,
               "hourly_units": {"wind_speed_100m": "m/s", "temperature_2m": "°C"},
               "hourly": {"time": times, "wind_speed_100m": [7] * 48, "temperature_2m": [2] * 48}}
    wind, temperature, selected, checks = validate_hourly(payload, ORIGIN)
    assert len(wind) == len(temperature) == len(selected) == checks["coverage_count"] == 48
    assert selected[0] == "2026-01-30T19:00:00Z"
    del payload["hourly"]["time"][-1]
    del payload["hourly"]["wind_speed_100m"][-1]
    del payload["hourly"]["temperature_2m"][-1]
    with pytest.raises(WeatherBlocked):
        validate_hourly(payload, ORIGIN)


def test_conservative_schedule_selects_latest_eligible_cycle(tmp_path: Path):
    eligible, checks = ordered_candidates(Settings(tmp_path), "turbine_1", ORIGIN)
    assert eligible[0].isoformat() == "2026-01-30T06:00:00+00:00"
    assert checks[0]["availability_status"] == "ineligible"  # 18 UTC
    assert checks[1]["available_by_utc"] == "2026-01-30T19:05:00Z"  # 12 UTC
    assert checks[1]["availability_status"] == "ineligible"
    assert checks[2]["available_by_utc"] == "2026-01-30T12:22:00Z"  # 06 UTC
    assert checks[2]["availability_status"] == "eligible"
    evidence = weather._evidence(Settings(tmp_path), "turbine_1", eligible[0])
    assert availability_verdict(eligible[0], ORIGIN, evidence)[0] == "eligible"
    assert availability_verdict(eligible[0], ORIGIN, {**evidence, "available_by_utc": "2026-01-30T07:00:00Z"})[0] == "unverified"


def test_ineligible_raw_weather_is_saved_without_predictions(tmp_path: Path):
    run = datetime.fromisoformat("2026-01-30T12:00:00+00:00")
    start = run
    raw = json.dumps({"latitude": 43.62, "longitude": 78.48, "elevation": 1000,
                      "timezone": "GMT", "utc_offset_seconds": 0,
                      "hourly_units": {"wind_speed_100m": "m/s", "temperature_2m": "°C"},
                      "hourly": {"time": [(start + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(96)],
                                 "wind_speed_100m": [7] * 96, "temperature_2m": [2] * 96}}).encode()
    with pytest.raises(WeatherBlocked) as caught:
        retrieve(Settings(tmp_path), "turbine_1", ORIGIN, run, fetcher=lambda *_: (raw, 200, 0))
    assert caught.value.code == "WEATHER_RUN_NOT_ELIGIBLE"
    snapshot_id = caught.value.details["weather_snapshot_id"]
    folder = Settings(tmp_path).artifacts_dir / "weather"
    assert (folder / f"{snapshot_id}.json").read_bytes() == raw
    manifest = json.loads((folder / f"{snapshot_id}.manifest.json").read_text(encoding="utf-8"))
    assert manifest["raw_sha256"] == hashlib.sha256(raw).hexdigest()
    assert manifest["coverage_count"] == 48
    assert manifest["availability_evidence"]["evidence_type"] == "conservative_schedule_delay_bound"
    assert manifest["available_by_utc"] == "2026-01-30T19:05:00Z"


def test_eligible_weather_provenance_is_immutable(tmp_path: Path):
    run = datetime.fromisoformat("2026-01-30T06:00:00+00:00")
    start = ORIGIN.astimezone(timezone.utc)
    raw = json.dumps({"latitude": 43.62, "longitude": 78.48, "elevation": 1000,
                      "timezone": "GMT", "utc_offset_seconds": 0,
                      "hourly_units": {"wind_speed_100m": "m/s", "temperature_2m": "°C"},
                      "hourly": {"time": [(start + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(48)],
                                 "wind_speed_100m": [7] * 48, "temperature_2m": [2] * 48}}).encode()
    settings = Settings(tmp_path)
    first = retrieve(settings, "turbine_1", ORIGIN, run, fetcher=lambda *_: (raw, 200, 0))
    folder = settings.artifacts_dir / "weather"
    manifest_path = folder / f"{first.metadata['weather_snapshot_id']}.manifest.json"
    original_manifest = manifest_path.read_bytes()
    second = retrieve(settings, "turbine_1", ORIGIN, run, fetcher=lambda *_: (raw, 200, 0))
    assert second.metadata["weather_snapshot_id"] == first.metadata["weather_snapshot_id"]
    assert manifest_path.read_bytes() == original_manifest
    assert (folder / f"{first.metadata['weather_snapshot_id']}.json").read_bytes() == raw
    assert first.metadata["eligibility"] == "eligible"
    assert first.metadata["available_by_utc"] == "2026-01-30T12:22:00Z"
    assert first.metadata["selected_valid_times_utc"][0] == "2026-01-30T19:00:00Z"
    assert first.metadata["coverage_count"] == 48


def test_two_turbine_shape_and_blocked_behavior(tmp_path: Path, monkeypatch):
    for i in (1, 2):
        make_csv_portable(tmp_path / "data" / f"dataset_{i}.csv")
    settings = Settings(tmp_path)

    def eligible(*args):
        tid = args[2]
        return WeatherSnapshot({"weather_snapshot_id": f"snapshot-{tid}", "run_at_utc": "2026-01-30T12:00:00Z",
                                "raw_path": str(tmp_path / "raw.json")}, [7] * 48, [2] * 48)

    monkeypatch.setattr("agentic_forecast.agents._retrieve_first", eligible)
    result = run_first_origin(settings)
    assert result["status"] == "completed"
    assert len(result["forecasts"]) == 96
    assert result["farm_aggregate"] is None
    assert result["farm_aggregate_reason"]["code"] == "AGGREGATION_RULE_UNAVAILABLE"
    for tid in ("turbine_1", "turbine_2"):
        rows = [row for row in result["forecasts"] if row["turbine_id"] == tid]
        assert [row["lead_hours"] for row in rows] == list(range(1, 49))
        assert all(rows[i]["valid_end"] == rows[i + 1]["valid_start"] for i in range(47))
        assert sum(row["in_test_period"] for row in rows) == 24
        assert all(row["actual_power_normalized"] is None for row in rows)

    def blocked(*args):
        raise WeatherBlocked("AVAILABILITY_UNVERIFIED", "No publication record")

    monkeypatch.setattr("agentic_forecast.agents._retrieve_first", blocked)
    blocked_result = run_first_origin(settings)
    assert blocked_result["status"] == "blocked"
    assert blocked_result["forecasts"] == []
    assert len(blocked_result["errors"]) == 2


def test_api_contract(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(api, "settings", Settings(tmp_path))
    monkeypatch.setattr(api.executor, "submit", lambda *_: None)
    monkeypatch.setattr(api, "active_run", None)
    client = TestClient(api.app)
    context = client.get("/api/context")
    assert context.status_code == 200
    assert context.json()["turbines"][0]["coordinate"] == {"latitude": 43.64513889, "longitude": 78.53561111}
    assert context.json()["turbines"][1]["coordinate"] == {"latitude": 43.64319444, "longitude": 78.53883333}
    assert context.json()["capabilities"]["replay"] is True
    assert client.get("/api/runs/" + "0" * 32).status_code == 404
    assert client.post("/api/runs", json={"mode": "replay", "from_origin": "2026-02-03T00:00:00+05:00",
                                           "through_origin": "2026-02-02T00:00:00+05:00"}).status_code == 422
    assert client.post("/api/runs", json={"mode": "single", "origin_at": "2026-01-31T01:00:00+05:00"}).status_code == 422
    accepted = client.post("/api/runs", json={"mode": "single", "origin_at": ORIGIN.isoformat()})
    assert accepted.status_code == 202
    assert client.get(accepted.json()["poll_url"]).json()["status"] == "queued"
    assert client.post("/api/runs", json={"mode": "single", "origin_at": ORIGIN.isoformat()}).status_code == 409
    assert client.get(accepted.json()["poll_url"]).json()["farm_aggregate_reason"]["code"] == "AGGREGATION_RULE_UNAVAILABLE"
    monkeypatch.setattr(api, "active_run", None)
    replay = client.post("/api/runs", json={"mode": "replay"})
    assert replay.status_code == 202
    assert client.get(replay.json()["poll_url"]).json()["progress"]["total_origins"] == 29
    saved = {"run_id": "a" * 32, "schema_version": "1.0", "status": "blocked", "forecasts": [],
             "errors": [{"code": "AVAILABILITY_UNVERIFIED", "severity": "error", "message": "No record"}]}
    RunStore(Settings(tmp_path)).save(saved)
    assert client.get("/api/runs/" + "a" * 32).json() == saved


def test_newer_cycle_with_missing_coverage_falls_back(tmp_path: Path, monkeypatch):
    newer = datetime.fromisoformat("2026-01-30T12:00:00+00:00")
    older = datetime.fromisoformat("2026-01-30T06:00:00+00:00")
    monkeypatch.setattr(agents, "ordered_candidates", lambda *_: ([newer, older], []))
    tried = []

    def fake_retrieve(_settings, _turbine, _origin, run, **_kwargs):
        tried.append(run)
        if run == newer:
            raise WeatherBlocked("WEATHER_COVERAGE_INCOMPLETE", "Missing hour")
        return WeatherSnapshot({"run_at_utc": "2026-01-30T06:00:00Z", "retries_used": 0}, [7] * 48, [2] * 48)

    monkeypatch.setattr(agents, "retrieve", fake_retrieve)
    result = initial_result("a" * 32, ORIGIN)
    assert agents._retrieve_first(Settings(tmp_path), result, "turbine_1", ORIGIN).metadata["run_at_utc"] == "2026-01-30T06:00:00Z"
    assert tried == [newer, older]
    assert result["agent"]["decisions"][0]["action"] == "select_older_eligible_run"
    monkeypatch.setattr(agents, "retrieve", lambda *_args, **_kwargs: (_ for _ in ()).throw(
        WeatherBlocked("WEATHER_COVERAGE_INCOMPLETE", "Missing hour")))
    with pytest.raises(WeatherBlocked):
        agents._retrieve_first(Settings(tmp_path), initial_result("b" * 32, ORIGIN), "turbine_1", ORIGIN)


def test_frozen_weather_ignores_changed_upstream_response(tmp_path: Path):
    run = datetime.fromisoformat("2026-01-30T06:00:00+00:00")
    start = ORIGIN.astimezone(timezone.utc)
    payload = {"timezone": "GMT", "utc_offset_seconds": 0,
               "hourly_units": {"wind_speed_100m": "m/s", "temperature_2m": "°C"},
               "hourly": {"time": [(start + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(48)],
                          "wind_speed_100m": [7] * 48, "temperature_2m": [2] * 48}}
    raw = json.dumps(payload).encode()
    settings = Settings(tmp_path)
    first = retrieve(settings, "turbine_1", ORIGIN, run, fetcher=lambda *_: (raw, 200, 0))
    payload["hourly"]["wind_speed_100m"] = [12] * 48
    changed_raw = json.dumps(payload).encode()
    fetch_calls = []

    def changed_fetcher(*_args):
        fetch_calls.append(1)
        return changed_raw, 200, 0

    second = retrieve(settings, "turbine_1", ORIGIN, run, fetcher=changed_fetcher)
    assert fetch_calls == []
    assert second.wind == first.wind == [7] * 48
    assert second.metadata["weather_snapshot_id"] == first.metadata["weather_snapshot_id"]
    assert second.metadata["reused_snapshot"] is True
    assert second.metadata["availability_method"] == "schedule_bound"
    assert second.metadata["availability_evidence"]["documented_provider_delay_minutes"] == 360
    assert second.metadata["availability_evidence"]["safety_margin_minutes"] == 10
    assert second.metadata["coverage_end_utc"] == "2026-02-01T19:00:00Z"


@pytest.mark.parametrize("status", [400, 401, 403, 404, 405, 409, 422])
def test_permanent_http_errors_do_not_retry(status, monkeypatch):
    calls = []

    def reject(*_args, **_kwargs):
        calls.append(1)
        raise urllib.error.HTTPError("https://example.test", status, "permanent", {}, None)

    monkeypatch.setattr(weather.urllib.request, "urlopen", reject)
    with pytest.raises(WeatherBlocked):
        weather._fetch("https://example.test", 1, 2)
    assert len(calls) == 1


@pytest.mark.parametrize("status", [408, 425, 429, 500, 502, 503, 504])
def test_transient_http_errors_retry(status, monkeypatch):
    calls = []

    class Response:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def read(self):
            return b"ok"

    def serve(*_args, **_kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise urllib.error.HTTPError("https://example.test", status, "transient", {"Retry-After": "1"}, None)
        return Response()

    monkeypatch.setattr(weather.urllib.request, "urlopen", serve)
    monkeypatch.setattr(weather.time, "sleep", lambda *_: None)
    assert weather._fetch("https://example.test", 1, 2) == (b"ok", 200, 1)
    assert len(calls) == 2


def test_network_timeout_retries(monkeypatch):
    calls = []
    monkeypatch.setattr(weather.time, "sleep", lambda *_: None)

    def timeout(*_args, **_kwargs):
        calls.append(1)
        raise TimeoutError("timed out")

    monkeypatch.setattr(weather.urllib.request, "urlopen", timeout)
    with pytest.raises(weather.WeatherUnavailable):
        weather._fetch("https://example.test", 1, 2)
    assert len(calls) == 3


def test_prediction_blocked_failed_and_changed_input_recalculation(tmp_path: Path, monkeypatch):
    for i in (1, 2):
        make_csv_portable(tmp_path / "data" / f"dataset_{i}.csv")
    settings = Settings(tmp_path)

    def eligible(*args):
        tid = args[2]
        return WeatherSnapshot({"weather_snapshot_id": f"snapshot-{tid}", "run_at_utc": "2026-01-30T06:00:00Z",
                                "raw_path": str(tmp_path / "raw.json"), "requested_coordinate": {"latitude": 43.6},
                                "availability_method": "schedule_bound"}, [7] * 48, [2] * 48)

    monkeypatch.setattr(agents, "_retrieve_first", eligible)
    first = run_first_origin(settings)
    assert first["status"] == "completed"
    original_predict = agents.predict
    monkeypatch.setattr(agents, "predict", lambda *_: (_ for _ in ()).throw(AssertionError("unnecessary prediction")))
    same = run_first_origin(settings)
    assert same["status"] == "completed"
    assert all(item["action"] == "reuse_unchanged_calculation" for item in same["agent"]["decisions"][:2])
    assert [row["power_normalized"] for row in same["forecasts"]] == [row["power_normalized"] for row in first["forecasts"]]
    monkeypatch.setattr(agents, "predict", original_predict)
    source = tmp_path / "data" / "dataset_1.csv"
    lines = source.read_text(encoding="utf-8").splitlines()
    cells = next(csv.reader([lines[1]]))
    cells[2] = "5"
    lines[1] = ",".join(cells)
    source.write_text("\n".join(lines) + "\n", encoding="utf-8")
    changed = run_first_origin(settings)
    assert changed["status"] == "completed"
    assert any(item["action"] == "recalculate" and item["turbine_id"] == "turbine_1"
               for item in changed["agent"]["decisions"])
    assert changed["agent"]["decisions"][-1]["recalculation_count"] == 1
    assert changed["forecasts"][0]["previous_run_id"] == same["run_id"]
    assert changed["forecasts"][0]["revision_delta"] is not None
    assert RunStore(settings).load(first["run_id"])["status"] == "completed"

    monkeypatch.setattr(agents, "predict", lambda *_: (_ for _ in ()).throw(ValueError("out of [0,1]")))
    blocked = run_first_origin(Settings(tmp_path / "blocked"), preloaded={
        tid: load_turbine(tmp_path / "data" / f"dataset_{tid[-1]}.csv", tid, ZONE) for tid in ("turbine_1", "turbine_2")})
    assert blocked["status"] == "blocked"
    assert all(error["code"] == "FORECAST_OUTPUT_INVALID" for error in blocked["errors"])
    assert blocked["farm_aggregate"] is None
    assert blocked["farm_aggregate_reason"]["code"] == "INCOMPLETE_TURBINE_PREDICTIONS"

    monkeypatch.setattr(agents, "predict", lambda *_: (_ for _ in ()).throw(RuntimeError("unexpected")))
    failed = run_first_origin(Settings(tmp_path / "failed"), preloaded={
        tid: load_turbine(tmp_path / "data" / f"dataset_{tid[-1]}.csv", tid, ZONE) for tid in ("turbine_1", "turbine_2")})
    assert failed["status"] == "failed"
    assert all(error["code"] == "MODEL_RUNTIME_ERROR" for error in failed["errors"])


def test_replay_visits_all_29_origins_and_counts_outcomes(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(agents, "load_all", lambda *_: {})
    visited = []

    def fake_origin(_settings, run_id=None, origin=None, preloaded=None):
        visited.append(origin.isoformat())
        child = initial_result(f"{len(visited):032x}", origin)
        child["status"] = "blocked" if len(visited) == 2 else "failed" if len(visited) == 3 else "completed"
        child["turbine_outcomes"] = {"turbine_1": child["status"], "turbine_2": child["status"]}
        return child

    monkeypatch.setattr(agents, "run_first_origin", fake_origin)
    result = run_replay(Settings(tmp_path))
    assert len(visited) == len(set(visited)) == len(result["origins"]) == 29
    assert result["summary"] == {"total_origins": 29, "success": 27, "blocked": 1, "failed": 1,
                                 "with_farm_aggregate": 0, "without_farm_aggregate": 29}
    assert sum(result["progress"][key] for key in ("completed_origins", "blocked_origins", "failed_origins")) == 29
    assert all(item["status"] in ("completed", "blocked", "failed") for item in result["origins"])
