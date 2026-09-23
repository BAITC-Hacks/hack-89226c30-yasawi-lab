# Agentic Wind Farm Forecasting

Yasawi Lab's implementation for the HackAlem AI Energy task: forecast normalized hourly generation for a two-turbine wind farm over the next 24–48 hours.

## Problem analysis

The supplied files contain 10-minute wind speed, normalized active power, and ambient temperature for two turbines. The task requires a forecast every day from the historical forecast origin, using only information that would have been available at that moment. The result must be reproducible, auditable, and runnable by technical experts from the repository.

The first prototype exposed four important failure modes:

1. Missing hourly records meant that a positional `lag_24` was not always 24 hours ago.
2. Training used measured weather while prediction sometimes used a weather fallback.
3. A recursive one-step model accumulated errors over a 24–48 hour horizon.
4. Forecast inputs and their origin were not sufficiently auditable.

This version addresses each issue as an explicit agent stage.

## Agentic workflow and solved problems

### Stage 1 Data quality agent

**Problem solved:** irregular timestamps and silent data gaps.

Each turbine is aggregated to a complete 1-hour index. Missing weather values may be interpolated for feature construction, but missing power values are never invented. The system records missing rows and refuses to use incomplete target windows for training.

Output evidence is stored in the forecast manifest under `data_quality`.

### Stage 2 Weather retrieval agent

**Problem solved:** using weather that was not available at the forecast moment.

For each forecast origin, the agent requests hourly wind speed and temperature for both turbine coordinates from the Open-Meteo historical forecast endpoint and averages the two locations. Requests are cached by forecast interval in `outputs/weather_cache`.

The forecast manifest records whether weather came from the archive, cache, or the deterministic seasonal fallback. The fallback exists for offline development; it is not the preferred competition mode. For final replay, cache the exact archived forecast vintage for every origin before running the model. Open-Meteo documentation: [Historical Forecast API](https://open-meteo.com/en/docs/historical-forecast-api).

### Stage 3 Feature engineering agent

**Problem solved:** row-based lags and a weak representation of wind generation.

The model now uses true hourly lags at 1, 2, 3, 6, 12, 24, and 48 hours; rolling power averages; wind speed; temperature; calendar features; and a cubic wind power-curve feature. Because the timeline is reindexed first, a 24-hour lag means exactly 24 hours.

### Stage 4 Direct multi-horizon forecasting agent

**Problem solved:** recursive error accumulation.

Instead of one one-step model repeatedly predicting itself, the system trains one regularized ridge model for each horizon. The 1-hour model predicts hour 1, the 2-hour model predicts hour 2, and so on through hour 24 or 48. This allows each horizon to learn its own error profile and avoids forcing every horizon to share the same coefficients.

### Stage 5 Sequential replay agent

**Problem solved:** failure to reproduce the required daily operating cycle.

The replay command forecasts one day at a time. After each origin, only prior predictions are added to the working history; future observed power is never added. Every row contains `forecast_origin`, and the manifest records `no_lookahead: true`.

### Stage 6 Validation and audit agent

**Problem solved:** no evidence that the model is better than a simple baseline and no trace of the exact run.

The system writes a CSV forecast and a JSON manifest containing the cutoff, horizon, coordinates, source files, weather source, data quality report, training counts, model description, and stage statuses. The development backtest reports MAE, RMSE, WMAPE, actual mean, and prediction mean.

The backtest command currently uses observed future weather to isolate model quality. Competition validation must replace it with the archived forecast vintage for that historical origin; using later observations would violate the task rules.

## Architecture

```text
CSV turbine histories
        |
        v
DataAgent -> complete hourly timeline -> DataQualityAgent
        |
        +--> WeatherAgent -> archived hourly weather + cache
        |
        v
Feature engineering -> direct horizon models -> forecast CSV
        |
        v
Validation and audit manifest
```

## Coordinates

The task document supplies these locations:

- Turbine 1: `43.645150, 78.535604`
- Turbine 2: `43.643198, 78.538828`

They are configured in `src/agentic_forecast/config.py`.

## Installation

Python 3.10+ is required.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

Dependencies are intentionally small: NumPy and pandas. The ridge solver uses `numpy.linalg.solve`, so the core workflow does not require a heavyweight ML framework.

## Commands

Single 24-hour forecast from the end of the supplied history:

```powershell
python -m agentic_forecast.cli --cutoff "2026-01-31 23:00" --horizon 24
```

Single 48-hour forecast:

```powershell
python -m agentic_forecast.cli --cutoff "2026-01-31 23:00" --horizon 48
```

Sequential February replay:

```powershell
python -m agentic_forecast.cli --replay-start 2026-02-01 --replay-end 2026-02-28 --horizon 48
```

Development backtest from a historical origin:

```powershell
python -m agentic_forecast.cli --backtest-start "2026-01-01 00:00" --horizon 24
```

The backtest is labelled as a proxy because it uses known future weather. It is useful for model debugging, not a substitute for archived forecast replay.

## Outputs

- `outputs/forecast.csv`: timestamp, forecast weather, and normalized farm power forecast.
- `outputs/forecast_manifest.json`: provenance, data quality, stage statuses, and training sample counts.
- `outputs/replay_forecast.csv`: sequential replay output with a forecast origin for every row.
- `outputs/weather_cache/`: cached weather responses. This directory is ignored by Git until the team deliberately packages the required archive.

## Verification performed

The revised implementation has been checked with:

- a 24-hour single forecast;
- a 48-hour single forecast;
- a two-day sequential replay; and
- a 24-hour historical proxy backtest starting on 1 January 2026.

That proxy backtest produced MAE `0.1355`, RMSE `0.1658`, and WMAPE `0.2199` using observed future weather. These numbers are development evidence only: final competition metrics must be recomputed with the archived forecast weather available at each origin.

The current restricted execution environment could not reach the weather archive, so the generated manifests correctly identify `seasonal-persistence-fallback`. This is a visible warning, not a hidden substitution. Before submission, the team should populate `outputs/weather_cache` with the exact historical forecast vintages and confirm that the manifest reports archive or cache usage.

## Competition compliance checklist

- [x] Uses both supplied turbine histories.
- [x] Produces hourly 24–48 hour forecasts.
- [x] Uses turbine coordinates to retrieve weather.
- [x] Separates forecast origin from future target data.
- [x] Supports sequential daily replay.
- [x] Provides a reproducible README and manifest.
- [ ] Package exact archived forecast vintages for every final replay origin.
- [ ] Run final validation with those archived vintages and report metrics.

The last two items require the archive data to be available and should be completed before submission. The supplied target data ends on 31 January 2026, so February target accuracy cannot be measured from the provided files alone.
