from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentic_forecast import api
from agentic_forecast.config import CONFIGURATION_ID, DEFAULT_FRONTEND_ORIGINS, default_settings


def test_frontend_origins_default_to_local_development(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("FRONTEND_ORIGIN", raising=False)
    assert default_settings(tmp_path).frontend_origins == DEFAULT_FRONTEND_ORIGINS


def test_frontend_origins_can_be_configured(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://wind.example.test/, http://localhost:3000, https://wind.example.test")
    assert default_settings(tmp_path).frontend_origins == ("https://wind.example.test", "http://localhost:3000")


@pytest.mark.parametrize("origin", ["*", "https://*.example.test", "https://wind.example.test/path", "https://user:secret@wind.example.test", ""])
def test_frontend_origins_reject_non_origins(monkeypatch, tmp_path: Path, origin: str):
    monkeypatch.setenv("FRONTEND_ORIGIN", origin)
    with pytest.raises(ValueError, match="FRONTEND_ORIGIN"):
        default_settings(tmp_path)


def test_context_exposes_request_configuration_and_browser_cors():
    origin = api.settings.frontend_origins[0]
    client = TestClient(api.app)
    response = client.get("/api/context", headers={"Origin": origin})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "access-control-allow-credentials" not in response.headers
    context = response.json()
    assert context["configuration_id"] == CONFIGURATION_ID
    request = api.RunRequest(mode="single", origin_at=context["origin_range"]["first"],
                             configuration_id=context["configuration_id"])
    assert request.configuration_id == CONFIGURATION_ID
    assert context["project_timezone"] == "Asia/Almaty"
    assert context["horizon_hours"] == 48
    assert {item["turbine_id"] for item in context["turbines"]} == {"turbine_1", "turbine_2"}
    assert context["capabilities"]["single_run"] is True
    assert context["capabilities"]["replay"] is True


def test_run_preflight_allows_json_post_only_for_configured_origin():
    client = TestClient(api.app)
    headers = {"Origin": api.settings.frontend_origins[0], "Access-Control-Request-Method": "POST",
               "Access-Control-Request-Headers": "content-type"}
    response = client.options("/api/runs", headers=headers)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == headers["Origin"]
    assert "POST" in response.headers["access-control-allow-methods"]
    rejected = client.options("/api/runs", headers={**headers, "Origin": "https://unconfigured.example.test"})
    assert rejected.status_code == 400
    assert "access-control-allow-origin" not in rejected.headers
