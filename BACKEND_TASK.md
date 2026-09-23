# Wind Replay — backend technical specification

**Status:** specification only; implementation requires approval. The official source is [task.md](task.md). Dataset facts below come from a complete scan of both files in `data/`. Project choices are identified separately from official requirements. External API mechanics are referenced to the [Open-Meteo Single Runs documentation](https://open-meteo.com/en/docs/single-runs-api); they are not claims made by the official task.

## 1. Backend Goal

Build one FastAPI process that uses the supplied turbine histories to fit a forecast model, obtains archived weather *forecast runs* for the two task coordinates, and produces a 48-hour sequence of hourly **normalized active power** predictions per turbine. Replay one origin at 00:00 Asia/Almaty on 31 January 2026, then each day through 28 February 2026. At every origin, inputs and model training data must have been knowable by that origin. Expose structured run results, provenance, progress, and explicit blocked/failure reasons to the existing React screen. Store local artifacts sufficient to reproduce a run. Do not present turbine predictions as a station total because no aggregation rule or normalization denominator was supplied.

**Requirement versus MVP choice:** `task.md` requires an hourly horizon of **24–48 hours**. The project-selected **48 hours** lies inside that official range; the task does not demand separate 24-hour and 48-hour modes. The **Agentic AI cycle is mandatory**. Optional OpenAI means only that a hosted LLM is optional; it does not make autonomous orchestration or the trained forecasting model optional.

The official task asks for hourly wind-farm generation forecasting, an autonomous weather→preparation→model→forecast→analysis→recalculation cycle, and historical replay for the February test period. It does **not** specify an ML family, provider, coordinates in decimal form, timezone, model accuracy threshold, or February actual generation values. Source: `task.md`, *Описание задачи*, *Предоставляемые данные*, and *Задача участников*.

## 2. Official Requirements Traceability

| Official requirement | Backend responsibility | How it will be verified |
| --- | --- | --- |
| Forecast hourly wind-farm output 24–48 hours ahead (`task.md`, *Описание задачи*) | Return 48 consecutive hourly normalized-power predictions for each mapped turbine, with an explicit hour interval and lead number. | Shape test: 48 intervals per turbine, contiguous and ordered. |
| Build a model from provided history (`task.md`, *Задача участников* 1) | Read both CSVs without editing them, aggregate to hours, fit one model per turbine using only allowed pre-origin records. | Model manifests show file hashes, cutoff, row counts, features and version; cutoff test. |
| Retrieve open-source weather forecasts by turbine coordinates (`task.md`, *Задача участников* 2) | Call the pinned Open-Meteo Single Runs model at each task coordinate; preserve both request and response. | Provider adapter test and stored request/response per turbine. |
| Weather had to be available at forecast time (`task.md`, paragraphs after numbered list) | Validate run **availability**, not merely initialization, against each origin; block if eligibility cannot be evidenced. | Before/after-origin eligibility tests and audit metadata. |
| Next 24–48 hours, hourly (`task.md`, *Задача участников* 3) | Extract the 48 hourly intervals beginning at the origin. | Every interval has weather inputs and one prediction; no gaps or duplicate hours. |
| Agentic full cycle (`task.md`, *Задача участников* 4) | Execute bounded retrieval, preparation, forecasting, analysis and input-update/recalculation decisions with recorded stages. | Run manifest shows stages, decisions, retries and revision links; no manual step in the normal path. |
| Replay 31 January, 1 February, then sequentially through February (`task.md`, replay paragraphs) | Process 29 daily origins in order, 31 Jan–28 Feb inclusive; track origin-level outcomes. | Replay test verifies 29 ordered origins and progress totals. |
| Forecast test period 1–28 February 2026 (`task.md`, *Описание задачи*) | Mark an output interval as in-test only if its **valid start** falls within February; retain all 48-hour windows, including edge hours outside February. | Boundary tests for 31 Jan and 28 Feb. |
| Official scoring (`task.md`, final table) | Support a runnable scenario, auditable architecture, reproducibility, practical output and a focused approach. | 25 task/workability + 25 technical + 25 README/reproducibility + 15 value/applicability + 10 development/originality = 100. These are evaluation criteria, not extra backend features. |

The official scoring table assigns **25 points** to task compliance/workability, **25** to technical implementation (explicitly including AI/agentic AI), **25** to README/reproducibility, **15** to value/applicability, and **10** to development potential/originality. A specification alone earns none of these points; judges must be able to run and inspect the implemented workflow. For Agentic AI specifically, the demo must show an autonomous run progressing through weather retrieval, data preparation, model execution, hourly forecast, result analysis, and a bounded decision to retry or recalculate when eligible inputs change. Source: `task.md`, final scoring table and *Задача участников* 4.

## 3. Confirmed Assumptions and Unresolved Limitations

**Official facts (`task.md`):** Two turbine coordinate links are supplied; the fields are statistical time, average wind speed, normalized active power on the line side, and average ambient temperature. Historical records end 31 January 2026. The test period is February 2026; historical weather forecasts available at each origin are required. The 24–48 hour hourly horizon and agentic cycle are required.

**Confirmed project decisions (conversation):** `dataset_1.csv` maps to Turbine 1; `dataset_2.csv` maps to Turbine 2. Predict normalized active power per turbine, with historical average wind speed and ambient temperature as predictors. Choose 48 hours, daily origins 31 Jan–28 Feb, Open-Meteo Single Runs, ECMWF IFS HRES, `wind_speed_100m` and `temperature_2m`. Keep `wind_speed_10m` only as optional diagnostic. Interpret CSV time as configurable `Asia/Almaty` / UTC+05:00. Use one React app, one FastAPI process and local artifacts; no NVIDIA API. OpenAI is optional for grounded orchestration/explanation, never numerical forecasting.

**Unresolved limitations:** CSV time carries no timezone or interval-definition metadata. CSV wind sensor height, power normalization formula/denominator, turbine capacity and station-level aggregation rule are unknown. The task gives map links, not inline numeric coordinates; resolve both links and record the resulting numbers with source evidence before weather retrieval. Exact historical publication/availability time for each weather run needs independent evidence; `run=` and a later successful archive retrieval alone do not prove it. There are no February 2026 actual power rows in either `data/` CSV.

## 4. Data Sources

| Source | Content and role | Boundary |
| --- | --- | --- |
| `data/dataset_1.csv` | 142,360 ten-minute records, 11 Mar 2023 00:00 through 31 Jan 2026 23:50; Turbine 1 by project decision. | Read-only history. |
| `data/dataset_2.csv` | 149,499 records over the same first/last timestamps; Turbine 2 by project decision. | Read-only history. |
| `task.md`, *Предоставляемые данные* | [Turbine 1 map coordinate](https://maps.app.goo.gl/iN6svMt69D5qRpFU9) and [Turbine 2 map coordinate](https://maps.app.goo.gl/8UQMwsYavY6nLvFY8). | Decimal latitude/longitude must be verified from these links before use. |
| [Open-Meteo Single Runs API](https://open-meteo.com/en/docs/single-runs-api) | Archived individual ECMWF IFS HRES forecast runs. | External forecast input; never replace with observed future weather. |

Both CSVs have **exactly five columns**, in order: `ID`, `Статистическое время` (Statistical Time), `Средняя скорость ветра(m/s)` (Average Wind Speed), `Нормализованная активная мощность` (Normalized Active Power), and `Средняя температура окружающей среды(°C)` (Average Ambient Temperature). All five columns are populated in the supplied files; timestamps and numeric cells parse; no full-row, ID or timestamp duplicates were found within either file. `ID` starts at 1 in **each** file and is only a record identifier. Never join turbines on ID. The timestamp is the temporal alignment key across files, with turbine identity retained; a timestamp join is not needed to fit separate turbine models. Observed normalized power is between 0 and 1 in both files, but its normalization formula is unknown. No geographic columns are in the CSVs. Neither file contains February rows.

The source cadence is mainly ten minutes, with gaps. Turbine 1 has 23,763 occupied hourly bins: 23,667 with six samples and 96 with fewer. Turbine 2 has 25,004 occupied bins: 24,785 with six samples and 219 with fewer. The full hourly index also has absent bins. These counts come from grouping every supplied row by floored statistical hour, without filling gaps.

## 5. CSV Processing

1. Open only the two named `data/` CSVs in read-only mode; preserve bytes and calculate SHA-256 for each source file. Do not use the similarly named files under `assets/` unless a future approved change explicitly replaces the data source.
2. Decode as UTF-8 with optional BOM. Require the five exact source headers above; report missing/extra/renamed headers. Do not silently select columns by position. Parse `ID` as integer; time with the observed `YYYY-MM-DD H:MM:SS` format; three measures as finite numbers. Keep original row number and raw timestamp for error reports.
3. Reject invalid timestamps, duplicate `(turbine_id, Statistical Time)` keys, non-finite measures and impossible negative wind speeds as source-quality errors; report counts and examples. A genuinely missing numeric cell remains missing. Do not silently coerce it to zero. `ID` uniqueness is checked within a dataset, but ID is excluded from features and joins.
4. Localize naive CSV timestamps using the configurable project timezone (`Asia/Almaty` default). Convert to UTC internally and retain both local and UTC forms. If a timestamp cannot be localized unambiguously, flag it and block affected records. This is a project assumption, never an official timezone claim.
5. **Project aggregation convention:** Treat each 10-minute timestamp as a sample inside the local clock-hour `[HH:00, HH+1:00)`. For each turbine/hour, compute arithmetic means independently for wind, temperature and normalized power from present valid source values. This is an hourly *mean power*, not energy. Record `raw_sample_count`, `sample_count` (rows with all three finite measures), and source timestamp range. Expected complete count is six distinct 10-minute slots, based on observed cadence; do not assume the official file defines energy-meter interval semantics.
6. Mark `INCOMPLETE_HOUR` if any of the six slots is absent or any required measure is invalid; mark `MISSING_HOUR` with count zero for an absent bin. Maintain a contiguous hourly index so gaps stay visible. Exclude incomplete and missing hours from fitting and holdout scoring; retain their quality records for the audit. No zero-filling, interpolation, forward-fill or back-fill of the power target. In particular, the zero values already present in the CSV are legitimate observed values, distinct from nulls.
7. Align weather forecast timestamps to the same *instant* in UTC, then display/derive calendar features in configured local time. Do not align by naive timestamp strings or assume the provider and CSV timezones match.

## 6. Model Training

**One model family:** scikit-learn `HistGradientBoostingRegressor` with squared-error loss and fixed, recorded hyperparameters/random seed. The observed wind–power relation is nonlinear, making this small tabular model a reasonable single-family MVP choice; this is a design choice, not an official model requirement. Fit **one separate final model per turbine**, without sharing targets or summing them. Keep the model class and feature definition fixed across all origins.

Features: hourly wind speed (m/s), hourly ambient temperature (°C), and optionally deterministic sine/cosine of local hour and day of year. If enabled, those calendar features must be generated identically in training and inference and listed in the manifest. No other measured future features. The target is hourly mean normalized active power. Do not use `ID`, future measured wind/temperature/power, post-origin samples, actual February values, turbine 2 target in turbine 1 model (or vice versa), or weather from a model run unavailable by the origin. Do not use target lags in this MVP; this avoids recursive look-ahead and makes the forecast-input contract transparent.

**Cutoff:** For each origin, include only training hours whose full interval has ended by the origin **and** whose source samples were available before it. At 31 Jan 00:00 local, the last permissible hour is 30 Jan 23:00–31 Jan 00:00; no 31 Jan daytime records may enter that model. For 1 Feb onward, source CSV ends 31 Jan 23:50; the fixed historical dataset is the upper limit. Do not fit on prior predictions as if they were observed power. A cached final model can be reused for later origins if its cutoff/hash/config match; retrain only when genuinely new eligible historical observations or configuration arrive.

For an honest pre-test check, hold out the latest 14 local calendar days **strictly before the first origin**, train on earlier complete hours, and report MAE and RMSE on eligible holdout hours per turbine. This 14-day split is an MVP evaluation convention, not an official holdout. Refit the final per-turbine model on all complete pre-origin hours for production. Record split boundaries, counts, metrics and whether measured historical weather was used in evaluation. Such metrics are **not** February replay accuracy because inference uses forecast weather and February actual generation is absent. If a split has insufficient complete rows to fit and score, report `evaluation.status=unavailable` rather than inventing a metric.

Version each model with turbine ID, training cutoff, dataset SHA-256, feature-set version, library version, parameters and deterministic seed. Save the fitted model plus a JSON manifest in `artifacts/models/`. Forecast outputs must be finite. A value outside the empirical 0–1 target range is flagged and blocks that origin until resolved; do not silently clamp or convert it to MW/MWh.

## 7. Historical Weather Adapter

Use `GET https://single-runs-api.open-meteo.com/v1/forecast` with the documented required `run=YYYY-MM-DDTHH:mm` **UTC initialization time**, explicit `models=ecmwf_ifs`, `hourly=wind_speed_100m,temperature_2m`, `timezone=UTC`, `wind_speed_unit=ms`, and the verified task latitude/longitude for each turbine. Ask for a range containing every required valid hour; validate response `hourly_units` rather than trusting requested units. The model identifier and endpoint should be checked against the live provider before implementation. `wind_speed_10m` can be requested and stored for diagnostics only; it must not enter the approved model. Open-Meteo documents archived IFS HRES 9 km runs from March 2024, 00/06/12/18 UTC cycles and hourly resolution over the first 48 hours. [Source](https://open-meteo.com/en/docs/single-runs-api).

For each replay origin, enumerate model cycles backwards from the origin; choose the **latest run with documented availability no later than the origin** and complete hourly coverage for both turbine coordinates. Prefer the same run for both turbines; if this is impossible, record separate run IDs and eligibility for each rather than blending them. Initialization before origin is necessary but insufficient: Open-Meteo says global runs usually require 4–6 hours after initialization before public availability, and exact availability is a separate timestamp. [Source](https://open-meteo.com/en/docs/single-runs-api). Its live [model-updates documentation](https://open-meteo.com/en/docs/model-updates) distinguishes `last_run_initialisation_time` from `last_run_availability_time`; a *current* metadata query does not establish a January/February 2026 availability timestamp.

Eligibility predicate per turbine: `(run_initialised_at_utc <= available_by_utc <= origin_utc) AND all 48 forecast valid hours exist and are finite AND the selected model/variables/units match`. If an exact historical `available_by_utc` or defensible contemporaneous publication record cannot be obtained, set `eligibility=unverified` and block the audited replay rather than infer availability from the run name, a typical delay, or retrieval date. Preserve candidate and rejection reasons. Do not substitute observed/reanalysis weather, an undated stitched Historical Forecast response, or a synthetic seasonal fallback into a completed replay.

The 48 intervals are `[origin + h hours, origin + (h+1) hours)` for `h=0..47`; `lead_hours=h+1`. Align one forecast weather value by its UTC valid timestamp to each `valid_start`. Keep provider UTC timestamps intact and convert copies to `Asia/Almaty` only for alignment/display. Reject missing/duplicate hours, null weather, wrong units or incomplete coverage; never interpolate an incomplete weather horizon silently. A 31 Jan 00:00 +05 origin is 30 Jan 19:00Z. Do **not** hard-code the example 30 Jan 12:00Z run as eligible until its availability evidence has been established.

## 8. Weather Provenance

Save one immutable weather snapshot per `(turbine, requested coordinate, model run, request parameters)` containing:

- provider name; model name and exact provider model identifier;
- full request URL and request parameter map, HTTP status, retrieval timestamp `retrieved_at_utc`, and source documentation/reference URL;
- requested latitude/longitude **per turbine**, returned provider-grid latitude/longitude/elevation if present, and provider response timezone/UTC offset;
- selected `run_initialised_at_utc`, historical `available_by_utc` if proven, availability-evidence type/source/timestamp, eligibility verdict and origin UTC;
- all returned raw valid timestamps in UTC, selected 48 timestamps, hourly variable names, units, heights (100 m wind; 2 m temperature), missing-value/coverage checks;
- raw response **bytes** (or exact UTF-8 body), their SHA-256 digest, and the path to the saved raw file.

The API's `run=` value represents initialization, not publication. `retrieved_at_utc` is today's archive retrieval and is not a historical availability timestamp. A hash alone does not preserve the raw response; store both. Redact any secrets from request URLs before persistence (none should be needed for the public MVP).

## 9. Forecasting Workflow

`CSV read-only load → schema/quality validation → hourly aggregation → strict pre-origin training cutoff → per-turbine model fit/load → candidate archived-weather retrieval → availability and 48-hour validation → aligned feature preparation → per-turbine numerical prediction → finite/range/shape validation → deterministic summary and revision analysis → bounded recalculation decision → atomic local artifact save → structured API result`.

At each daily origin, process both turbines; do not merge their weather rows even if Open-Meteo returns the same grid cell. Calculate only supported summaries: per-turbine hourly forecast, mean/min/max of normalized predictions, coverage counts and, when a previous origin forecasted the same valid hour, a revision difference on that normalized scale. No station aggregate, energy unit, capacity factor, cost or February error metric. The first 31 January 48-hour window includes hours outside February; mark each row's `in_test_period` from `valid_start`, not from the origin.

## 10. Agentic AI Workflow

This is a **mandatory autonomous agent workflow** around the learned forecasting model and external weather tool, implemented as a bounded state machine rather than a generic autonomous agent. One run request must trigger the full cycle without a developer manually initiating each stage. Stage names: `load_data`, `validate_data`, `aggregate_hourly`, `train_or_load_models`, `retrieve_weather`, `validate_eligibility`, `prepare_features`, `forecast`, `analyze`, `decide_recalculation`, `persist`. Record start/end UTC, status, input/output artifact references and a short factual decision reason per stage. This agent behavior and the ML forecaster are the project's AI/agentic AI implementation even when no OpenAI key is configured; a hosted LLM is an optional explanation layer.

Allowed decisions: `continue`, `retry_provider`, `select_older_eligible_run`, `recalculate_from_updated_eligible_input`, `block`, `fail`, `complete`. Retry transient provider/network errors at most twice with bounded timeouts; then fail that origin. Select an older run only when its **own** availability and full 48-hour coverage are evidenced. Recalculate at most once per origin when a changed input that was already eligible at that origin is detected, record `previous_run_id`/`revision_delta`, and never rewrite an earlier forecast with a later-known weather run. A later daily origin is a new forecast, and overlapping valid hours can be compared as revisions.

Schema failure, unproven historical availability, incomplete weather or unsupported input configuration lead to `blocked`; transport/model runtime faults after bounded retries lead to `failed`. Deterministic Python owns all eligibility, cutoffs, numerical forecasts, metrics, status transitions and recalculation gates. An optional LLM cannot override those gates.

## 11. OpenAI Integration

OpenAI is **optional**. If enabled, use a small, fast text model capable of structured JSON output/tool calling for evidence-grounded analysis of backend-computed facts and a suggested `completed`/`blocked`/`retry`/`recalculate` action. The deterministic state machine validates or rejects that suggestion. It may explain warnings and revisions in concise user-facing language. Send only compact run metadata, quality flags, summary metrics and provenance references; do not send raw CSVs or the full raw provider response. Never ask the LLM to invent the 48 numeric values, weather timestamps, availability proof, accuracy, or station total. If the API is absent or fails, a deterministic analysis string and decisions keep the run functional. No NVIDIA integration. Exact OpenAI model ID is a deployment choice; pin it in configuration/README if this optional integration is actually implemented.

## 12. API Contract

Use JSON with ISO 8601 timestamps carrying offset; provider originals use `Z`. Numeric forecast data lives only in typed fields. `schema_version="1.0"` matches the existing frontend mock. API `errors` and `warnings` are arrays of `{code, severity, message, details?}`; free-form analysis is display-only. CORS is limited to the local React origin in development. No auth in this MVP.

### `GET /api/context`

Purpose: discover the fixed demo configuration, available origin range and data limitations. Request: no body. `200` response: `{schema_version, project_timezone, horizon_hours:48, turbines:[{turbine_id,dataset_id,coordinate:{latitude,longitude},coordinate_source}], origin_range:{first,last,cadence:"daily"}, weather:{provider,model,variables}, capabilities:{single_run,replay,openai_enabled}, assumptions:[...], limitations:[...]}`. Coordinate values remain unavailable/null until the task links are verified; the endpoint must not pretend otherwise. `500` only for unexpected server fault; source/config failures should be represented explicitly in capabilities or errors.

### `POST /api/runs`

Purpose: start a single-origin forecast or sequential replay. Request schema: `{mode:"single"|"replay", origin_at?:"2026-01-31T00:00:00+05:00", from_origin?:"2026-01-31T00:00:00+05:00", through_origin?:"2026-02-28T00:00:00+05:00", configuration_id?:"approved-replay-v1"}`. `single` requires `origin_at`; `replay` uses the approved first/last origins unless explicitly narrowed within that range. Client may not supply weather values, turbine capacity or model family. Validate one origin per local day at 00:00 and fixed 48-hour horizon. A single process may run the work in a bounded in-process background task and write status to local JSON; no broker, distributed queue or worker service. Only one active replay is allowed.

`202` response: `{schema_version,run_id,status:"queued"|"running",poll_url:"/api/runs/{run_id}"}`. `422` invalid body/origin/config; `409` another run active; `500` cannot initialize local artifacts. Persist a run record before responding. If an implementation chooses synchronous execution for a single origin, it may instead return `201` with the same full result schema as `GET` and must document that choice; replay should remain pollable to avoid HTTP timeouts.

### `GET /api/runs/{run_id}`

Purpose: poll a run or retrieve its saved result. Request: path `run_id`, no body. `200` response mirrors `frontend/src/data/mockForecast.json` at top level:

| Field | Required content |
| --- | --- |
| `schema_version`, `run_id`, `status`, `mode`, `configuration_id`, `is_mock` | `is_mock=false` for real model output. |
| `progress` | `{completed_origins,blocked_origins,total_origins}`; add failed count if used. |
| `forecasts[]` | Typed rows `{dataset_id,turbine_id,origin_at,valid_start,valid_end,lead_hours,power_normalized,actual_power_normalized:null,weather_snapshot_id,model_version,in_test_period,previous_run_id,revision_delta,quality_flags:[]}`. Exactly 96 rows for a fully completed single 48-hour origin. For a replay, rows additionally distinguish origins. |
| `weather_snapshots[]` | IDs referenced by forecast rows plus provider/model, `run_at_utc`, proven `available_by_utc`, `retrieved_at_utc`, requested/provider coordinates, variables/units, source reference, raw response digest/path and availability evidence. A snapshot must identify one turbine's requested coordinate even if grid cells coincide. |
| `evaluation` | `{status,scope,mae,rmse,bias?,reason}`. February actual-based metrics are null/unavailable; pre-test validation is separately labeled. |
| `agent` | `{execution_mode,steps:[{name,status,started_at_utc?,ended_at_utc?,reason?}],analysis,decisions:[...]}`. |
| `warnings[]`, `errors[]` | Stable machine codes and readable messages, including assumption and blocked reasons. |

`404` for missing run ID; `500` only if a persisted run cannot be read. `queued`/`running` may return empty forecasts and current stages. `blocked`/`failed` never include fabricated forecasts for affected origins. `partial` includes successful origins/turbines and explicit failures for the rest. Backend must correct the current **illustrative** frontend mock's January `in_test_period=true` values before real integration; no numeric mock value is evidence of a model result.

## 13. Run Statuses

| Status | Meaning |
| --- | --- |
| `queued` | Request accepted and local run record created; work not yet started. No external queue service. |
| `running` | At least one stage is executing. |
| `completed` | Every requested origin and both turbines produced validated 48-hour forecasts with eligible weather evidence. |
| `partial` | Some requested origin/turbine units completed, others blocked or failed; never hide the missing units. |
| `blocked` | No usable forecast because a required fact/input/eligibility condition is absent or invalid; retrying the same unchanged input will not cure it. |
| `failed` | No usable forecast due to runtime/provider/model/storage fault after bounded retry. |

For a single origin with one successful turbine and one blocked/failed turbine, status is `partial`. For the 29-origin replay, totals count origins, while details list turbine-level outcomes.

## 14. Local Artifact Structure

```text
artifacts/
  weather/   # raw response per turbine/run, SHA-256, request and availability metadata
  models/    # two serialized final models plus manifests, training/split metrics
  runs/      # run JSON, per-origin stage/status JSON, forecast JSON/CSV as an export
  logs/      # bounded structured event/error log without secrets or raw CSV rows
```

Write artifacts atomically (temporary file then replace), use stable `run_id`, avoid overwriting a completed run, and link every forecast row to a saved model version and weather snapshot. Store enough configuration and file hashes to rerun with the same inputs. Local artifact persistence does not require a database.

## 15. Error Handling

| Condition | Required behavior |
| --- | --- |
| Invalid CSV schema, timestamp, duplicate key or unreadable file | Stop affected turbine; `blocked` or `partial`; list exact field/row examples without modifying source. |
| Missing/incomplete historical hours | Flag in hourly audit; exclude from fit/evaluation; block if too little complete training data. |
| No eligible historical weather run or unproven availability | `blocked`, code `WEATHER_RUN_NOT_ELIGIBLE` or `AVAILABILITY_UNVERIFIED`; report candidate runs and evidence gaps. |
| Incomplete 48-hour horizon, null variable, wrong units or returned model | Reject that candidate; try an older evidenced run, then block. Never fill future inputs from measurements. |
| Provider timeout/HTTP error | Two bounded retries; then `failed` with `WEATHER_PROVIDER_UNAVAILABLE`; keep any verifiable cached raw run for an explicit retry. |
| Invalid API timestamps/configuration | `422` with field-specific JSON errors; no run artifact if request is invalid. |
| Model fit or prediction fault/non-finite result | `failed` for that turbine/origin; record model version, stack trace in local log, safe API message. |
| Unknown run ID | `404` with `RUN_NOT_FOUND`. |

## 16. Testing Requirements

Minimum meaningful tests: exact CSV header/schema loading and read-only hash stability; 10-minute to hourly mean and `sample_count`; incomplete/missing-hour flags and no power zero-fill; Asia/Almaty↔UTC conversion with an origin boundary; model cutoff at 31 Jan 00:00 and absence of February/source leakage; historical weather initialization **and availability** eligibility, including an unverified run; 48-hour two-turbine shape/continuity; blocked behavior with no fabricated forecast; JSON API response validation and 404/422 cases. A local saved weather fixture must contain the exact raw response and provenance of an eligible run if tests need to avoid network dependence; a synthetic fixture can test logic but cannot prove historical eligibility in production.

## 17. First Milestone

For `2026-01-31T00:00:00+05:00`: read both `data/` CSVs; validate and aggregate separately; train the two final turbine models using only hours ending by the origin; retrieve a historically eligible archived forecast at each verified coordinate; save raw weather/provenance; return exactly 48 hourly normalized predictions per turbine in the API shape; save run/model/weather manifests; pass the tests above. The milestone is **blocked until numeric coordinates and historical availability evidence are resolved**. A run that lacks either must return a structured blocked result, not a successful forecast.

## 18. Acceptance Criteria

- [ ] Official task inputs and two dataset mappings are documented and enforced.
- [ ] Original CSV hashes are unchanged after running.
- [ ] Hourly aggregation exposes counts/quality flags; incomplete targets do not enter training.
- [ ] 31 Jan model cutoff excludes later 31 Jan records; later replay never learns from February predictions as truth.
- [ ] Both task coordinates are verified and preserved in each weather request/provenance record.
- [ ] Every completed forecast row links to a proven eligible archived run and raw response.
- [ ] Exactly 48 contiguous hourly normalized predictions per turbine for every completed origin.
- [ ] Daily replay covers 31 Jan–28 Feb in order; January/March edge hours are labeled outside test period.
- [ ] Agent stages, bounded retry/recalculation decisions and reasons are visible in JSON.
- [ ] No MW/MWh, capacity, station total or February accuracy is invented.
- [ ] Three API endpoints validate requests and return stable typed JSON matching the frontend contract.
- [ ] Blocked, partial and failed cases have no disguised fallback result.
- [ ] Offline unit tests and the first real origin pass; README lets a reviewer reproduce them.

## 19. Explicitly Out of Scope

NVIDIA API; database; Redis; Celery; external queues; WebSockets; RAG; chatbot; multi-agent framework; authentication; hyperparameter search; multiple model families; MW/MWh conversion; invented capacity or normalization formula; station-level aggregation without an official rule; maps and admin features; live weather or later measured weather as February replay inputs.

## 20. Implementation Order

1. Resolve and record decimal coordinates from both `task.md` map links and a defensible historical weather-availability evidence method. These are gates to a completed replay.
2. Freeze API DTOs against `frontend/src/data/mockForecast.json`; correct `in_test_period` semantics in backend output.
3. Implement strict read-only CSV validation, timezone localization and hourly aggregation with counts/flags.
4. Implement two turbine models, cutoff controls, temporal holdout and manifests.
5. Implement one-origin Single Runs adapter, raw cache and provenance; test eligibility and 48-hour alignment.
6. Implement bounded state machine and local run persistence; deliver the first origin.
7. Add the three FastAPI endpoints and connect the existing React adapter.
8. Extend to 29 sequential origins and revision comparisons.
9. Run tests, fix blocked/error cases and finish README. Add optional OpenAI explanation only if the deterministic workflow is stable.

## 21. Risks and Limitations

CSV wind sensor height is unknown; `wind_speed_100m` is an explicit MVP assumption and may shift predictions. The CSV timezone and hour-label semantics are assumed. The normalization formula/denominator and installed capacity are unknown. Measured historical weather used in training differs from forecast weather used in replay, so pre-test holdout errors may understate operational error. Turbine output cannot be aggregated into a justified station normalized value. February actual generation is unavailable, so February MAE/RMSE cannot be verified from supplied files. Exact historical availability evidence for archived model runs remains the most serious compliance risk; the Single Runs archive may provide a run without proving the moment it became accessible. External API/network failure and model/version changes can also prevent reproducibility unless raw responses are saved.

## 22. README Requirements for Backend

Document official problem and five scoring categories; source CSV paths/mapping/schema/date range and immutable hashes; both verified task coordinates with link references; all project assumptions (timezone, hourly bins, 100 m wind, normalized scale); weather provider/model/endpoint, run-selection and availability-evidence method; exact training cutoff and temporal validation meaning; one-model-per-turbine family/features/version; three endpoint request/response examples and error/status codes; `artifacts/` layout and provenance fields; environment variables (project timezone, API base URL, provider timeout, optional OpenAI key/model); install/start commands for one FastAPI process and React; offline tests and first-origin/replay demo commands; how to inspect an actual saved run; source licenses/third-party libraries; limitations including no February actual accuracy, no station total and measured-vs-forecast shift. Distinguish live model results from the frontend's mock JSON.
