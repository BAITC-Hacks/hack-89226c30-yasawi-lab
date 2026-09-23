import assert from "node:assert/strict";
import test from "node:test";
import { ApiError, createForecastClient } from "../src/api/forecast.js";

const context = {
  project_timezone: "Asia/Almaty",
  origin_range: { first: "2026-01-31T00:00:00+05:00", last: "2026-02-28T00:00:00+05:00" },
  turbines: [{ turbine_id: "turbine_1" }, { turbine_id: "turbine_2" }],
};
const json = (data, status = 200) => new Response(JSON.stringify(data), {
  status, headers: { "Content-Type": "application/json" },
});

test("context uses the API base URL and shares concurrent requests", async () => {
  const calls = [];
  const client = createForecastClient({ baseUrl: "http://localhost:8000/", fetchImpl: async (...args) => {
    calls.push(args);
    return json(context);
  } });
  const [first, second] = await Promise.all([client.getContext(), client.getContext()]);
  assert.deepEqual(first, context);
  assert.equal(first, second);
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], "http://localhost:8000/api/context");
  assert.equal(calls[0][1].method, "GET");
  assert.equal(calls[0][1].headers.Accept, "application/json");
});

test("single-origin and replay creation send the supplied JSON contract", async () => {
  const calls = [];
  const client = createForecastClient({ baseUrl: "", fetchImpl: async (...args) => {
    calls.push(args);
    return json({ run_id: "new-run", status: "queued" }, 202);
  } });
  for (const body of [
    { mode: "single", origin_at: context.origin_range.first },
    { mode: "replay", from_origin: context.origin_range.first, through_origin: context.origin_range.last },
  ]) {
    assert.equal((await client.createRun(body)).status, "queued");
    const [url, options] = calls.at(-1);
    assert.equal(url, "/api/runs");
    assert.equal(options.method, "POST");
    assert.equal(options.headers["Content-Type"], "application/json");
    assert.deepEqual(JSON.parse(options.body), body);
  }
});

test("polling preserves null aggregate and normalized-power values", async () => {
  let requested;
  const run = {
    run_id: "run/with space", status: "completed",
    forecasts: [{ turbine_id: "turbine_1", power_normalized: 0 }, { turbine_id: "turbine_2", power_normalized: null }],
    farm_aggregate: null,
    farm_aggregate_reason: { code: "AGGREGATION_RULE_UNAVAILABLE", message: "No station normalization denominator was supplied." },
  };
  const controller = new AbortController();
  const client = createForecastClient({ baseUrl: "", fetchImpl: async (url, options) => {
    requested = { url, options };
    return json(run);
  } });
  assert.deepEqual(await client.getRun(run.run_id, { signal: controller.signal }), run);
  assert.equal(requested.url, "/api/runs/run%2Fwith%20space");
  assert.equal(requested.options.signal, controller.signal);
});

test("structured API errors and validation lists remain readable", async () => {
  for (const [status, payload, message, code] of [
    [404, { detail: { code: "RUN_NOT_FOUND", message: "Run was not found" } }, "Run was not found", "RUN_NOT_FOUND"],
    [422, { detail: [{ loc: ["body", "origin_at"], msg: "Input should be a valid datetime" }] }, "body.origin_at: Input should be a valid datetime", "API_ERROR"],
    [500, { unexpected: true }, "Forecast service returned HTTP 500", "API_ERROR"],
  ]) {
    const client = createForecastClient({ fetchImpl: async () => json(payload, status) });
    await assert.rejects(client.getRun("example"), (error) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, status);
      assert.equal(error.code, code);
      assert.equal(error.message, message);
      return true;
    });
  }
});

test("a network failure produces a safe message and context can retry", async () => {
  let attempts = 0;
  const client = createForecastClient({ fetchImpl: async () => {
    attempts += 1;
    if (attempts === 1) throw new Error("internal network address or credential");
    return json(context);
  } });
  await assert.rejects(client.getContext(), (error) => {
    assert.equal(error.code, "API_UNAVAILABLE");
    assert.match(error.message, /could not be reached/);
    assert.doesNotMatch(error.message, /credential/);
    return true;
  });
  assert.deepEqual(await client.getContext(), context);
  assert.equal(attempts, 2);
});

test("invalid JSON and malformed successful responses are rejected", async () => {
  const invalidJson = createForecastClient({ fetchImpl: async () => new Response("<html>server error</html>", { status: 502 }) });
  await assert.rejects(invalidJson.getRun("example"), { code: "INVALID_API_RESPONSE", status: 502 });
  const invalidContract = createForecastClient({ fetchImpl: async () => json({ status: "unknown" }) });
  await assert.rejects(invalidContract.getContext(), { code: "INVALID_API_RESPONSE" });
  await assert.rejects(invalidContract.createRun({}), { code: "INVALID_API_RESPONSE" });
  await assert.rejects(invalidContract.getRun("example"), { code: "INVALID_API_RESPONSE" });
});

test("abort is preserved so cancellation does not become a service failure", async () => {
  const aborted = new DOMException("Request aborted", "AbortError");
  const client = createForecastClient({ fetchImpl: async () => { throw aborted; } });
  await assert.rejects(client.getRun("example"), (error) => error === aborted);
});
