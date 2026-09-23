# Wind Replay backend — first milestone

This repository implements the first backend milestone in [BACKEND_TASK.md](BACKEND_TASK.md) for the [HackAlem wind forecasting task](task.md). Backend code, tests, configuration, and artifacts live in `backend/`; the original CSVs remain in root `data/`. The official task requests hourly generation forecasting 24–48 hours ahead, an autonomous weather → preparation → model → forecast → analysis → recalculation workflow, and a historical February 2026 replay. This milestone handles only the first origin, **2026-01-31T00:00:00+05:00**, with a 48-hour horizon for two separate turbine outputs. The five judging categories are task/workability (25), technical implementation (25), README/reproducibility (25), value/applicability (15), and development potential/originality (10).

## Source data and fixed configuration

| Turbine | Read-only source | SHA-256 | Verified task coordinate |
| --- | --- | --- | --- |
| 1 | `data/dataset_1.csv` | `c4c341582fb2dd348b7187f0128cff265fe055f469413871ebb5db50eef58b5b` | [43.64513889, 78.53561111](https://maps.app.goo.gl/iN6svMt69D5qRpFU9) |
| 2 | `data/dataset_2.csv` | `820578cd18bb557cd30c2e102f3ae5a386dfc6c489a5a15743339c2b017305e5` | [43.64319444, 78.53883333](https://maps.app.goo.gl/8UQMwsYavY6nLvFY8) |

The decimals above are converted from the confirmed task coordinates: turbine 1 `43°38'42.5"N 78°32'08.2"E`, turbine 2 `43°38'35.5"N 78°32'19.8"E`. Both CSVs have the exact five headers checked in `data.py`: ID, statistical time, average wind speed, normalized active power, and average ambient temperature. They span 11 March 2023 to 31 January 2026 and contain no February actual generation. Files in `assets/` and old `outputs/` are not used by this backend.

CSV timestamps have no timezone metadata. The approved project convention treats them as `Asia/Almaty` local samples within each clock hour. This zone was UTC+06 before March 2024 and UTC+05 afterward; six samples at `2024-02-29 23:00–23:50` in each file are ambiguous at the offset transition and are rejected and recorded. This is a project time interpretation, not an official timestamp fact. The hour means are normalized **power**, not energy. Complete hours need six valid ten-minute slots. Missing and incomplete hours remain in the audit and are excluded from fitting. Zero measured power remains zero.

The CSV wind sensor height, normalization denominator, capacity, and station aggregation rule are unknown. The approved forecast input `wind_speed_100m` is therefore an explicit sensor-height assumption. Each result has `farm_aggregate: null` and a structured `AGGREGATION_RULE_UNAVAILABLE` reason. No station total, MW/MWh, or February actual-based accuracy is produced.

## Model and cutoff

One scikit-learn `HistGradientBoostingRegressor` is fitted per turbine with squared-error loss, fixed parameters and seed 42. Features are hourly wind speed and ambient temperature; the target is hourly mean normalized active power. ID, target lags, cross-turbine target values, and post-origin rows are excluded. The first-origin cutoff is the end of **2026-01-30 23:00–2026-01-31 00:00 local**. Model manifests record source hash, version, cutoff, training count, parameters, library version, and serialized model path.

The latest 14 full local calendar days before the first origin are held out for development checks; the final models are then refitted on all complete pre-origin hours. The recorded MAE/RMSE use measured historical wind and temperature and are **not** February replay accuracy. Inference requires an eligible archived forecast run. Predictions outside [0, 1] or non-finite values block the affected origin; there is no clamping.

## Weather eligibility and provenance

The adapter calls the [Open-Meteo Single Runs API](https://open-meteo.com/en/docs/single-runs-api) with `models=ecmwf_ifs`, UTC `run=`, `wind_speed_100m`, `temperature_2m`, UTC timezone, and m/s wind units at each verified coordinate. It stores the exact response bytes, SHA-256, request, returned grid coordinate, units, 48 selected UTC valid timestamps, and availability verdict in `backend/artifacts/weather/`. Transport is retried at most twice. An older cycle is selectable only when it has its own proven availability and full weather coverage.

Historical eligibility uses a conservative schedule bound, not an observed publication timestamp. For each ECMWF IFS HRES cycle, the adapter takes the later of the applicable [ECMWF dissemination time](https://confluence.ecmwf.int/pages/viewpage.action?pageId=540563877) and the initialization time plus Open-Meteo's documented upper-end six-hour [processing/public-availability delay](https://open-meteo.com/en/docs/single-runs-api), then adds a ten-minute safety margin. The bound, source URLs, candidate decisions, raw response hash, and selected 48-hour coverage are saved in the weather manifest. A cycle is eligible only when its bound is no later than the replay origin.

At the first origin (2026-01-30 19:00 UTC), the 12:00 UTC cycle's bound is 19:05 UTC, so it is ineligible. The 06:00 UTC cycle's bound is 12:22 UTC, so it is selected and provides 48 hours at both coordinates. This is a documented historical-eligibility assumption; the API does not expose an exact historical publication timestamp.

## Agentic workflow and artifacts

A single request drives the bounded state machine through `load_data`, `validate_data`, `aggregate_hourly`, `train_or_load_models`, `retrieve_weather`, `validate_eligibility`, `prepare_features`, `forecast`, `analyze`, `decide_recalculation`, and `persist`. Stages record timestamps, reasons, and artifact references. Transient provider failures are retried at most twice; unavailable or invalid inputs produce structured blocked or failed states. The first-origin run records zero recalculations. Detection and recalculation of a later changed eligible input are not implemented in this milestone. Optional OpenAI explanation is not enabled; numerical forecasts and gates are deterministic.

`backend/artifacts/models/` holds serialized turbine models and manifests; `backend/artifacts/weather/` holds raw archive responses and provenance; `backend/artifacts/runs/` holds atomic result JSON and per-turbine hourly quality CSV; `backend/artifacts/logs/` holds runtime traces. Earlier generated outputs were preserved in `backend/artifacts/legacy_outputs/`. `backend/artifacts/` is a local reproducibility output, excluded from Git except for the moved legacy outputs. Existing completed runs are not overwritten. The raw source CSVs are never written.

## Install and run

Use Python 3.10 or newer:

```powershell
cd backend
python -m pip install -e '.[test]'
python -m agentic_forecast.cli --first-origin
python -m uvicorn agentic_forecast.api:app --host 127.0.0.1 --port 8000
python -m pytest -q tests/test_first_milestone.py
```

The CLI prints its run ID, status, forecast-row count, and errors. Its saved JSON is `backend/artifacts/runs/<run_id>.json` relative to the repository root. These environment variables are supported: `WIND_PROJECT_TIMEZONE` (default `Asia/Almaty`), `WIND_WEATHER_BASE_URL` (default Single Runs endpoint), and `WIND_PROVIDER_TIMEOUT_SECONDS` (default 15). Changing timezone or provider is an unsupported configuration for the approved first milestone unless separately verified. No API key is required. Internet access and a valid TLS trust store are needed for live archive retrieval; the offline tests use exact local fixture bytes and provenance checks.

## API contract

Only the first single origin is enabled. Replay requests return 422 until the next milestone. CORS permits local Vite at `http://localhost:5173` or `http://127.0.0.1:5173`. There is no authentication in this MVP.

```http
GET /api/context
POST /api/runs
Content-Type: application/json

{"mode":"single","origin_at":"2026-01-31T00:00:00+05:00","configuration_id":"approved-replay-v1"}
GET /api/runs/<run_id>
```

`POST` returns 202 with `schema_version`, `run_id`, `status`, and `poll_url`; poll `GET /api/runs/{run_id}` for the saved result. Invalid mode/origin/config returns 422, concurrent active run 409, unknown run 404. The result includes typed `forecasts`, `weather_snapshots`, `model_manifests`, `data_quality`, `evaluation`, `agent`, `warnings`, and `errors`. It also includes `farm_aggregate: null` and `farm_aggregate_reason`. A real completed first-origin run returned this summary:

```json
{
  "schema_version": "1.0",
  "run_id": "3de7431b07104e6c8975ddacac9002f4",
  "status": "completed",
  "mode": "single",
  "is_mock": false,
  "progress": {"completed_origins": 1, "blocked_origins": 0, "failed_origins": 0, "total_origins": 1},
  "farm_aggregate": null,
  "farm_aggregate_reason": {"code": "AGGREGATION_RULE_UNAVAILABLE", "message": "No station aggregation rule or normalization denominator was supplied"}
}
```

This summary omits the 96 `forecasts` rows and model/data/weather manifests; the saved response contains them. Each turbine has 48 consecutive hourly normalized predictions with `weather_snapshot_id`, `model_version`, and `in_test_period`. The first 24 valid hours are January and have `in_test_period=false`; the next 24 are February and true.

## Verification and next step

Offline tests check exact schema/hash stability, missing and incomplete bins, zero preservation, the cutoff and UTC conversion, conservative schedule selection, 48-hour alignment, a synthetic two-turbine shape, blocked output, raw response preservation, and API 404/422 behavior. The live first-origin result is `backend/artifacts/runs/3de7431b07104e6c8975ddacac9002f4.json`: completed, 96 rows, with two raw weather responses and separate turbine models. The next milestone is the remaining daily origins and changed-input recalculation.

Third-party components: Python, pandas, NumPy, scikit-learn, FastAPI, Pydantic, Uvicorn, joblib, certifi, tzdata, pytest/httpx for tests, and Open-Meteo weather data. Observe the provider's published usage terms for deployment.
