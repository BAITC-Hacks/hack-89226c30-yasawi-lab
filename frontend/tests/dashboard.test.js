import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

// Explicit fixtures follow the backend response contract; no demo data is imported.
const origin = "2026-01-31T00:00:00+05:00";
const context = {
  configuration_id: "test-config", project_timezone: "Asia/Almaty", horizon_hours: 48,
  origin_range: { first: origin, last: "2026-02-28T00:00:00+05:00" },
  turbines: [
    { turbine_id: "turbine_1", dataset_id: "dataset_1.csv", coordinate: { latitude: 43.64513889, longitude: 78.53561111 } },
    { turbine_id: "turbine_2", dataset_id: "dataset_2.csv", coordinate: { latitude: 43.64319444, longitude: 78.53883333 } },
  ],
  capabilities: { single_run: true, replay: true },
};

function runFixture(status = "completed") {
  const completed = status === "completed";
  return {
    run_id: "a".repeat(32), mode: "single", origin_at: origin, status,
    forecasts: completed ? context.turbines.flatMap(({ turbine_id }, turbineIndex) => Array.from({ length: 48 }, (_, hour) => ({
      turbine_id, origin_at: origin,
      valid_start: new Date(Date.parse(origin) + hour * 3600000).toISOString(),
      valid_end: new Date(Date.parse(origin) + (hour + 1) * 3600000).toISOString(),
      lead_hours: hour + 1, power_normalized: turbineIndex ? 0.5 : 0.25,
      weather_snapshot_id: `weather-${turbine_id}`, model_version: `model-${turbine_id}`, quality_flags: [],
    }))) : [],
    summary: { forecast_rows: completed ? 96 : 0, per_turbine: {
      turbine_1: { mean: 0.25, min: 0.25, max: 0.25, coverage_count: 48 },
      turbine_2: { mean: 0.5, min: 0.5, max: 0.5, coverage_count: 48 },
    } },
    weather_snapshots: context.turbines.map(({ turbine_id, coordinate }) => ({
      weather_snapshot_id: `weather-${turbine_id}`, turbine_id, provider: "Open-Meteo",
      model: "ECMWF IFS HRES 9km", run_at_utc: "2026-01-30T06:00:00Z",
      retrieved_at_utc: "2026-09-23T12:00:00Z", requested_coordinate: coordinate,
      provider_grid_coordinate: { latitude: 43.620384, longitude: 78.47891 },
      variables: ["wind_speed_100m", "temperature_2m"],
      hourly_units: { wind_speed_100m: "m/s", temperature_2m: "°C" },
      raw_sha256: "b".repeat(64), source_reference: "https://open-meteo.com/en/docs/single-runs-api",
      availability_method: "schedule_bound", available_by_utc: "2026-01-30T12:22:00Z",
      availability_evidence: { interpretation: "Conservative replay eligibility bound, not an observed publication timestamp" },
      origin_utc: "2026-01-30T19:00:00Z", coverage_start_utc: "2026-01-30T19:00:00Z",
      coverage_end_utc: "2026-02-01T19:00:00Z", selection_reason: "latest eligible cycle with full required coverage",
      eligibility: "eligible", coverage_count: 48,
    })),
    farm_aggregate: null,
    farm_aggregate_reason: { code: "AGGREGATION_RULE_UNAVAILABLE", message: "The station aggregation rule was not supplied." },
    turbine_outcomes: { turbine_1: status, turbine_2: status },
    errors: completed ? [] : [{ code: status === "blocked" ? "WEATHER_RUN_NOT_ELIGIBLE" : "RUN_RUNTIME_ERROR",
      message: status === "blocked" ? "No eligible historical weather cycle covers this origin." : "The forecast calculation could not finish." }],
    warnings: [],
    agent: { steps: [{ name: "retrieve_weather", status: completed ? "completed" : status, reason: "Provider evidence checked" }],
      decisions: [{ action: "reuse_unchanged_calculation", reason: "Frozen inputs match" }] },
  };
}

let server;
let ForecastDashboard;
before(async () => {
  server = await createServer({
    root: fileURLToPath(new URL("..", import.meta.url)),
    server: { middlewareMode: true, watch: null },
    appType: "custom", logLevel: "error",
  });
  ({ ForecastDashboard } = await server.ssrLoadModule("/src/App.jsx"));
});
after(async () => { await server?.close(); });

function render(data, overrides = {}) {
  const controller = {
    context, run: data, data, error: null, busy: false, originDate: "2026-01-31",
    setOriginDate() {}, selectedOrigin: origin, setSelectedOrigin() {}, loadingDetail: false,
    execute() {}, retryContext() {}, ...overrides,
  };
  return renderToStaticMarkup(React.createElement(ForecastDashboard, { controller, initialLanguage: "en" }));
}

test("completed response renders 48 hours, both turbines and backend weather provenance", () => {
  const html = render(runFixture());
  for (const expected of ["Completed", "Turbine 1", "Turbine 2", "dataset_1.csv", "dataset_2.csv",
    "48 of 48 hours", "Open-Meteo", "ECMWF IFS HRES 9km", "wind_speed_100m", "temperature_2m",
    "43.645139", "78.535611", "bbbbbbbbbbbbbbbbbb", "model-turbine_1", "0.25",
    "schedule_bound", "12:22", "latest eligible cycle with full required coverage"]) {
    assert.ok(html.includes(expected), `Missing backend data: ${expected}`);
  }
  assert.match(html, /chart-primary-line/);
  assert.match(html, /chart-comparison-line/);
  assert.doesNotMatch(html, /MOCK DATA|UI PREVIEW|undefined|NaN/);
});

test("null station aggregate displays the backend's structured reason", () => {
  const html = render(runFixture());
  assert.ok(html.includes("AGGREGATION_RULE_UNAVAILABLE"));
  assert.ok(html.includes("The station aggregation rule was not supplied."));
});

test("a genuine zero aggregate remains numeric and has no unavailable reason", () => {
  const data = runFixture();
  data.farm_aggregate = 0;
  data.farm_aggregate_reason = null;
  const html = render(data);
  const aggregate = html.match(/aria-label="Farm aggregate"([\s\S]*?)<\/article>/)?.[1];
  assert.match(aggregate, /<h2>0\.00<\/h2>/);
  assert.doesNotMatch(aggregate, /unavailable|AGGREGATION_RULE_UNAVAILABLE|detail-copy/);
});

test("summary values come from the backend and missing power is not rendered as zero", () => {
  const data = runFixture();
  data.summary.per_turbine.turbine_1.mean = 0.13;
  data.summary.per_turbine.turbine_1.max = 0.91;
  data.forecasts[0].power_normalized = null;
  const html = render(data);
  const summary = html.match(/class="chart-summary"([\s\S]*?)<\/article>/)?.[1];
  assert.match(summary, /<strong>0\.13<\/strong>/);
  assert.match(summary, /<strong>0\.91<\/strong>/);
  assert.match(html, /47 of 48 hours/);
  const firstRow = html.match(/<tbody><tr>([\s\S]*?)<\/tr>/)?.[1];
  assert.match(firstRow, /<td><strong>—<\/strong><\/td>/);
  assert.doesNotMatch(firstRow, /table-bar|0\.00/);
});

test("blocked and failed responses show their errors without forecast curves", () => {
  for (const [status, title, error] of [
    ["blocked", "Forecast blocked", "WEATHER_RUN_NOT_ELIGIBLE"],
    ["failed", "Run failed", "RUN_RUNTIME_ERROR"],
  ]) {
    const html = render(runFixture(status));
    assert.ok(html.includes(title));
    assert.ok(html.includes(error));
    assert.doesNotMatch(html, /chart-primary-line|chart-comparison-line/);
  }
});

test("replay renders backend totals and selected origin detail", () => {
  const detail = runFixture();
  const replay = { ...detail, mode: "replay", status: "partial", run_id: "c".repeat(32),
    origins: [{ origin_at: origin, status: "completed", run_id: detail.run_id }],
    summary: { total_origins: 29, success: 27, blocked: 1, failed: 1, with_farm_aggregate: 0, without_farm_aggregate: 29 },
  };
  const html = render(detail, { run: replay });
  assert.match(html, /replay-summary/);
  assert.match(html, /<strong>29<\/strong>/);
  assert.match(html, /<strong>27<\/strong>/);
  assert.match(html, /<option[^>]*value="2026-01-31T00:00:00\+05:00"/);
  assert.match(html, /chart-primary-line/);
});

test("initial loading and unreachable backend have distinct visible states", () => {
  assert.match(render(null, { context: null, run: null, data: null }), /Loading replay evidence/);
  const html = render(null, { context: null, run: null, data: null,
    error: { code: "API_UNAVAILABLE", message: "Connection unavailable" } });
  assert.match(html, /API_UNAVAILABLE/);
  assert.match(html, /Retry loading/);
  assert.doesNotMatch(html, /chart-primary-line/);
});
