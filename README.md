# Wind Replay backend

This repository implements the backend in [BACKEND_TASK.md](BACKEND_TASK.md) for the [HackAlem wind forecasting task](task.md). Backend code, tests, configuration, and artifacts live in `backend/`; the original CSVs remain in root `data/`. It produces 48 hourly normalized-power predictions for each turbine at the first origin, **2026-01-31T00:00:00+05:00**, and at every local midnight through **2026-02-28T00:00:00+05:00**. The five judging categories are task/workability (25), technical implementation (25), README/reproducibility (25), value/applicability (15), and development potential/originality (10).

## Source data and fixed configuration

| Turbine | Read-only source | SHA-256 | Verified task coordinate |
| --- | --- | --- | --- |
| 1 | `data/dataset_1.csv` | `c4c341582fb2dd348b7187f0128cff265fe055f469413871ebb5db50eef58b5b` | [43.64513889, 78.53561111](https://maps.app.goo.gl/iN6svMt69D5qRpFU9) |
| 2 | `data/dataset_2.csv` | `820578cd18bb557cd30c2e102f3ae5a386dfc6c489a5a15743339c2b017305e5` | [43.64319444, 78.53883333](https://maps.app.goo.gl/8UQMwsYavY6nLvFY8) |

The decimals above are converted from the confirmed task coordinates: turbine 1 `43°38'42.5"N 78°32'08.2"E`, turbine 2 `43°38'35.5"N 78°32'19.8"E`. Both CSVs have the exact five headers checked in `data.py`: ID, statistical time, average wind speed, normalized active power, and average ambient temperature. They span 11 March 2023 to 31 January 2026 and contain no February actual generation. Files in `assets/` and old `outputs/` are not used by this backend.

CSV timestamps have no timezone metadata. The approved project convention treats them as `Asia/Almaty` local samples within each clock hour. This zone was UTC+06 before March 2024 and UTC+05 afterward; six samples at `2024-02-29 23:00–23:50` in each file are ambiguous at the offset transition and are rejected and recorded. This is a project time interpretation, not an official timestamp fact. The hour means are normalized **power**, not energy. Complete hours need six valid ten-minute slots. Missing and incomplete hours remain in the audit and are excluded from fitting. Zero measured power remains zero.

The CSV wind sensor height, normalization denominator, capacity, and station aggregation rule are unknown. The approved forecast input `wind_speed_100m` is therefore an explicit sensor-height assumption. Each result has `farm_aggregate: null` and a structured reason: `AGGREGATION_RULE_UNAVAILABLE` when both turbines forecast successfully, or `INCOMPLETE_TURBINE_PREDICTIONS` if a turbine is blocked or fails. Null never means zero. No station total, MW/MWh, or February actual-based accuracy is produced.

## Model and cutoff

One scikit-learn `HistGradientBoostingRegressor` is fitted per turbine with squared-error loss, fixed parameters and seed 42. Features are hourly wind speed and ambient temperature; the target is hourly mean normalized active power. ID, target lags, cross-turbine target values, and post-origin rows are excluded. The first-origin cutoff is the end of **2026-01-30 23:00–2026-01-31 00:00 local**. Model manifests record source hash, version, cutoff, training count, parameters, library version, and serialized model path.

The latest 14 full local calendar days before each origin are held out for development checks; final models are then refitted on all complete pre-origin hours. Later origins may include 31 January actuals, but never February predictions as training truth. The recorded MAE/RMSE use measured historical wind and temperature and are **not** February replay accuracy. Inference requires an eligible archived forecast run. Predictions outside [0, 1] or non-finite values block the affected origin; there is no clamping.

## Weather eligibility and provenance

The adapter calls the [Open-Meteo Single Runs API](https://open-meteo.com/en/docs/single-runs-api) with `models=ecmwf_ifs`, UTC `run=`, `wind_speed_100m`, `temperature_2m`, UTC timezone, and m/s wind units at each verified coordinate. It stores the exact response bytes, SHA-256, endpoint/request parameters, requested and returned grid coordinates, model/cycle, units, retrieval time, 48 selected UTC valid timestamps, coverage interval, and availability verdict in `backend/artifacts/weather/`. Only transient HTTP 408/425/429/5xx-listed errors and network/timeouts are retried, at most twice; permanent 4xx responses fail immediately for that candidate. A bounded `Retry-After` is honored when supplied.

Historical eligibility accepts an exact documented timestamp recorded by the origin **or** a conservative schedule bound. For each ECMWF IFS HRES cycle, the adapter computes `max(ECMWF nominal release, cycle initialization + Open-Meteo six-hour upper-end delay) + 10-minute project safety margin`. Sources are the [ECMWF dissemination schedule](https://confluence.ecmwf.int/pages/viewpage.action?pageId=540563877) and [Open-Meteo processing/public-availability documentation](https://open-meteo.com/en/docs/single-runs-api). The separate source URLs, nominal release, documented delay, safety margin, calculated bound, method (`exact_timestamp` or `schedule_bound`), candidate decisions, selection reason, and coverage are stored as structured provenance. The ten minutes are this project's margin, not a provider claim. Candidate cycles are considered newest first; a run must clear the bound **and** cover all 48 hours, otherwise the adapter tries an older eligible cycle.

At the first origin (2026-01-30 19:00 UTC), the 12:00 UTC cycle's bound is 19:05 UTC, so it is ineligible. The 06:00 UTC cycle's bound is 12:22 UTC, so it is selected and provides 48 hours at both coordinates. This is a documented historical-eligibility assumption; the API does not expose an exact historical publication timestamp.

The first selected raw response and manifest for a turbine, origin, and request are pinned in `backend/artifacts/weather/selected/`. A historical rerun reads and validates that frozen response, its digest, coverage, and evidence; newer upstream bytes cannot silently replace it. A corrupt frozen snapshot fails explicitly. Weather snapshots remain separate from calculation results.

## Agentic workflow and artifacts

A single origin drives the bounded state machine through `load_data`, `validate_data`, `aggregate_hourly`, `train_or_load_models`, `retrieve_weather`, `validate_eligibility`, `prepare_features`, `forecast`, `analyze`, `decide_recalculation`, and `persist`. Replay invokes this same path sequentially for all 29 origins. Stages record timestamps, reasons, and artifact references. `completed` means valid predictions; `blocked` means historical eligibility, validation, or model-supported prediction range prevents them; `failed` means an unexpected runtime or infrastructure problem. Partial origin results expose the missing turbine and reason.

Each turbine calculation fingerprints its origin, source CSV hash, model version, selected frozen weather snapshot, and requested coordinate. A repeat with the same fingerprint reuses its 48 validated values. A changed effective input triggers prediction again, records a `recalculate` decision, `previous_run_id`, and per-hour `revision_delta`; the prior run JSON is retained. New upstream weather bytes do not change the frozen snapshot or trigger a historical revision. Optional OpenAI explanation is disabled; numerical forecasts and gates are deterministic.

`backend/artifacts/models/` holds serialized turbine models and manifests; `backend/artifacts/weather/` holds raw archive responses and provenance; `backend/artifacts/runs/` holds atomic result JSON and per-turbine hourly quality CSV; `backend/artifacts/logs/` holds runtime traces. Earlier generated outputs were preserved in `backend/artifacts/legacy_outputs/`. `backend/artifacts/` is a local reproducibility output, excluded from Git except for the moved legacy outputs. Existing completed runs are not overwritten. The raw source CSVs are never written.

## Install and run

Use Python 3.10 or newer:

```powershell
cd backend
python -m pip install -e '.[test]'
python -m agentic_forecast.cli --first-origin
python -m agentic_forecast.cli --replay
python -m uvicorn agentic_forecast.api:app --host 127.0.0.1 --port 8000
python -m pytest -q tests
```

The CLI prints its run ID, status, forecast-row count, progress, summary, and errors. Its saved JSON is `backend/artifacts/runs/<run_id>.json` relative to the repository root. The replay file contains all 29 per-origin details and counts; child run JSONs are retained alongside it. These environment variables are supported: `WIND_PROJECT_TIMEZONE` (default `Asia/Almaty`), `WIND_WEATHER_BASE_URL` (default Single Runs endpoint), and `WIND_PROVIDER_TIMEOUT_SECONDS` (default 15). Changing timezone or provider is unsupported for the approved configuration unless separately verified. No API key is required. Internet access and a valid TLS trust store are needed for live archive retrieval; offline tests use local fixture bytes and provenance checks.

## API contract

Single requests accept any approved local-midnight origin from 31 January through 28 February 2026. Replay requests cover all 29 by default or a validated contiguous subrange. CORS permits local Vite at `http://localhost:5173` or `http://127.0.0.1:5173`. There is no authentication in this MVP.

```http
GET /api/context
POST /api/runs
Content-Type: application/json

{"mode":"single","origin_at":"2026-01-31T00:00:00+05:00","configuration_id":"approved-replay-v1"}
{"mode":"replay","from_origin":"2026-01-31T00:00:00+05:00","through_origin":"2026-02-28T00:00:00+05:00","configuration_id":"approved-replay-v1"}
GET /api/runs/<run_id>
```

`POST` returns 202 with `schema_version`, `run_id`, `status`, and `poll_url`; poll `GET /api/runs/{run_id}` for the saved result. Invalid mode/origin/config returns 422, concurrent active run 409, unknown run 404. The result includes typed `forecasts`, `weather_snapshots`, `model_manifests`, `data_quality`, `evaluation`, `agent`, `warnings`, and `errors`. It also includes `farm_aggregate: null` and `farm_aggregate_reason`.

`GET /api/context` returns `schema_version: "1.0"`, `project_timezone: "Asia/Almaty"`, `horizon_hours: 48`, the two verified coordinates and dataset IDs, the `ecmwf_ifs` weather configuration, and `capabilities: {"single_run": true, "replay": true, "openai_enabled": false}`. An accepted `POST /api/runs` returns, for example, `{"schema_version":"1.0","run_id":"<new run ID>","status":"queued","poll_url":"/api/runs/<new run ID>"}`. `GET /api/runs/<run_id>` returns the full saved result, with this real completed-run summary:

```json
{
  "schema_version": "1.0",
  "run_id": "e1f69877a650409893aa2dee2d121395",
  "status": "completed",
  "mode": "single",
  "is_mock": false,
  "progress": {"completed_origins": 1, "blocked_origins": 0, "failed_origins": 0, "total_origins": 1},
  "farm_aggregate": null,
  "farm_aggregate_reason": {"code": "AGGREGATION_RULE_UNAVAILABLE", "message": "No station aggregation rule or normalization denominator was supplied"}
}
```

This summary omits the 96 `forecasts` rows and model/data/weather manifests; the saved response contains them. Each turbine has 48 consecutive hourly normalized predictions with `weather_snapshot_id`, `model_version`, and `in_test_period`. The first 24 valid hours are January and have `in_test_period=false`; the next 24 are February and true. The repository currently has no `frontend/` directory, so there is no frontend start command to verify here.

## Verification and next step

Offline tests check source schema/hash stability, hourly quality, cutoff, exact and schedule eligibility, cycle fallback, 48-hour alignment, snapshot immutability under changed upstream bytes, retry classification, blocked/failed semantics, changed-input recalculation, replay counts, and API responses. The live first-origin result is `backend/artifacts/runs/e1f69877a650409893aa2dee2d121395.json`: completed, 96 rows, with two raw weather responses at the confirmed coordinates and separate turbine models. The live full replay is `backend/artifacts/runs/69a6b12d95414c8e9480192824692b78.json`: 29 successful origins, 0 blocked, 0 failed, 2,784 turbine-hour predictions, 0 farm aggregates, and 29 explicit null-aggregate reasons. Its `origins[]` has a child run ID, selected weather provenance, prediction status, and outcome for every origin.

Third-party components: Python, pandas, NumPy, scikit-learn, FastAPI, Pydantic, Uvicorn, joblib, certifi, tzdata, pytest/httpx for tests, and Open-Meteo weather data. Observe the provider's published usage terms for deployment.
