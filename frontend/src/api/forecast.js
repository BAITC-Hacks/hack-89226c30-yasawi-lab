/** Central client for the existing FastAPI contract. Empty base means same origin. */
const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL || "").replace(/\/$/, "");
const statuses = new Set(["queued", "running", "completed", "partial", "blocked", "failed"]);

export class ApiError extends Error {
  constructor(message, status = null, code = "API_UNAVAILABLE") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

function errorMessage(body, status) {
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (detail?.message) return detail.message;
  if (Array.isArray(detail)) return detail.map((item) => `${item.loc?.join(".") || "request"}: ${item.msg}`).join("; ");
  return `Forecast service returned HTTP ${status}`;
}

export function createForecastClient({ baseUrl = API_BASE_URL, fetchImpl = globalThis.fetch } = {}) {
  const base = baseUrl.replace(/\/$/, "");
  let contextPromise;
  async function request(path, { method = "GET", body, signal } = {}) {
    let response;
    try {
      response = await fetchImpl(`${base}${path}`, {
        method, signal, headers: { Accept: "application/json", ...(body ? { "Content-Type": "application/json" } : {}) },
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
    } catch (error) {
      if (error.name === "AbortError") throw error;
      throw new ApiError("The forecast service could not be reached. Check the connection and retry.");
    }
    let payload;
    try { payload = await response.json(); }
    catch { throw new ApiError(`Forecast service returned invalid JSON (HTTP ${response.status})`, response.status, "INVALID_API_RESPONSE"); }
    if (!response.ok) throw new ApiError(errorMessage(payload, response.status), response.status, payload?.detail?.code || "API_ERROR");
    return payload;
  }
  return {
    getContext() {
      contextPromise ||= request("/api/context").then((data) => {
        if (!data.origin_range?.first || !Array.isArray(data.turbines) || !data.project_timezone) {
          throw new ApiError("Forecast context is incomplete", null, "INVALID_API_RESPONSE");
        }
        return data;
      }).catch((error) => { contextPromise = null; throw error; });
      return contextPromise;
    },
    async createRun(body, options = {}) {
      const data = await request("/api/runs", { ...options, method: "POST", body });
      if (!data.run_id || !statuses.has(data.status)) throw new ApiError("Invalid run acknowledgement", null, "INVALID_API_RESPONSE");
      return data;
    },
    async getRun(runId, options = {}) {
      const data = await request(`/api/runs/${encodeURIComponent(runId)}`, options);
      if (!statuses.has(data.status) || !Array.isArray(data.forecasts) || !data.run_id) {
        throw new ApiError("Invalid forecast run response", null, "INVALID_API_RESPONSE");
      }
      return data;
    },
  };
}

export const forecastApi = createForecastClient();
