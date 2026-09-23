import mockRun from "../data/mockForecast.json";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

export async function getForecastRun(runId = mockRun.run_id) {
  if (!API_BASE_URL) {
    await new Promise((resolve) => window.setTimeout(resolve, 320));
    return structuredClone(mockRun);
  }

  const response = await fetch(`${API_BASE_URL}/api/runs/${runId}`);
  if (!response.ok) {
    throw new Error(`Forecast API returned ${response.status}`);
  }
  return response.json();
}
