from __future__ import annotations

import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict

from .agents import RunStore, initial_result, issue, now_utc, run_first_origin, run_replay
from .config import COORDINATES, CONFIGURATION_ID, FIRST_ORIGIN, LAST_ORIGIN, default_settings


settings = default_settings()
app = FastAPI(title="Wind Replay backend", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=list(settings.frontend_origins),
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
executor = ThreadPoolExecutor(max_workers=1)
active_lock = threading.Lock()
active_run: str | None = None


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str
    origin_at: datetime | None = None
    from_origin: datetime | None = None
    through_origin: datetime | None = None
    configuration_id: str = CONFIGURATION_ID


@app.get("/api/context")
def context() -> dict:
    return {"schema_version": "1.0", "configuration_id": CONFIGURATION_ID,
            "project_timezone": settings.timezone, "horizon_hours": 48,
            "turbines": [{"turbine_id": tid, "dataset_id": f"dataset_{tid[-1]}.csv",
                          "coordinate": {"latitude": value[0], "longitude": value[1]}, "coordinate_source": value[2]}
                         for tid, value in COORDINATES.items()],
            "origin_range": {"first": FIRST_ORIGIN, "last": LAST_ORIGIN, "cadence": "daily"},
            "weather": {"provider": "Open-Meteo Single Runs", "model": "ecmwf_ifs",
                        "variables": ["wind_speed_100m", "temperature_2m"]},
            "capabilities": {"single_run": True, "replay": True, "openai_enabled": False},
            "assumptions": ["CSV timestamps are Asia/Almaty local samples within their clock hour",
                            "100 m forecast wind substitutes for wind at unknown CSV sensor height"],
            "limitations": ["Historical run eligibility uses a conservative ECMWF dissemination plus Open-Meteo delay bound, not an observed publication timestamp",
                            "No February actual power, station total, or MW/MWh conversion"]}


def _execute(run_id: str, mode: str, first: datetime, last: datetime) -> None:
    global active_run
    try:
        if mode == "replay":
            run_replay(settings, run_id, first, last)
        else:
            run_first_origin(settings, run_id, first)
    except Exception:
        log_path = settings.artifacts_dir / "logs" / f"{run_id}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as target:
            target.write(traceback.format_exc() + "\n")
        result = RunStore(settings).load(run_id) or initial_result(run_id, first, mode)
        result["status"] = "failed"
        result["progress"]["failed_origins"] = result["progress"]["total_origins"] - result["progress"]["completed_origins"] - result["progress"]["blocked_origins"]
        result["farm_aggregate_reason"] = {"code": "INCOMPLETE_TURBINE_PREDICTIONS",
                                           "message": "The run failed before all turbine predictions were available"}
        result["errors"].append(issue("RUN_RUNTIME_ERROR", "Unexpected backend run fault; inspect local logs"))
        result["ended_at_utc"] = now_utc()
        RunStore(settings).save(result)
    finally:
        with active_lock:
            active_run = None


@app.post("/api/runs", status_code=202)
def create_run(request: RunRequest) -> dict:
    global active_run
    if request.mode not in ("single", "replay"):
        raise HTTPException(422, detail={"code": "MODE_INVALID", "message": "mode must be single or replay"})
    if request.configuration_id != CONFIGURATION_ID:
        raise HTTPException(422, detail={"code": "CONFIGURATION_INVALID", "message": "Unsupported configuration_id"})
    def valid_origin(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != settings.first_origin.utcoffset():
            raise HTTPException(422, detail={"code": "ORIGIN_INVALID", "message": "Origin must carry the approved +05:00 offset"})
        local = value.astimezone(settings.zone)
        if (local.hour, local.minute, local.second, local.microsecond) != (0, 0, 0, 0) or not settings.first_origin <= local <= datetime.fromisoformat(LAST_ORIGIN).astimezone(settings.zone):
            raise HTTPException(422, detail={"code": "ORIGIN_INVALID", "message": f"Origin must be local midnight from {FIRST_ORIGIN} through {LAST_ORIGIN}"})
        return local
    if request.mode == "single":
        if request.origin_at is None or request.from_origin is not None or request.through_origin is not None:
            raise HTTPException(422, detail={"code": "ORIGIN_INVALID", "message": "single mode requires origin_at only"})
        first = last = valid_origin(request.origin_at)
    else:
        if request.origin_at is not None:
            raise HTTPException(422, detail={"code": "ORIGIN_INVALID", "message": "replay mode uses from_origin and through_origin"})
        first = valid_origin(request.from_origin or settings.first_origin)
        last = valid_origin(request.through_origin or datetime.fromisoformat(LAST_ORIGIN))
        if last < first:
            raise HTTPException(422, detail={"code": "ORIGIN_INVALID", "message": "through_origin precedes from_origin"})
    total = (last.date() - first.date()).days + 1
    with active_lock:
        if active_run is not None:
            raise HTTPException(409, detail={"code": "RUN_ACTIVE", "message": "Another run is active"})
        run_id = uuid.uuid4().hex
        try:
            RunStore(settings).save(initial_result(run_id, first, request.mode, total))
        except OSError as exc:
            raise HTTPException(500, detail={"code": "ARTIFACT_INIT_FAILED", "message": str(exc)}) from exc
        active_run = run_id
        executor.submit(_execute, run_id, request.mode, first, last)
    return {"schema_version": "1.0", "run_id": run_id, "status": "queued", "poll_url": f"/api/runs/{run_id}"}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    if not (len(run_id) == 32 and all(c in "0123456789abcdef" for c in run_id)):
        raise HTTPException(404, detail={"code": "RUN_NOT_FOUND", "message": "Unknown run ID"})
    try:
        result = RunStore(settings).load(run_id)
    except (OSError, ValueError) as exc:
        raise HTTPException(500, detail={"code": "RUN_READ_FAILED", "message": str(exc)}) from exc
    if result is None:
        raise HTTPException(404, detail={"code": "RUN_NOT_FOUND", "message": "Unknown run ID"})
    return result
