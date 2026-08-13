from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import get_settings


@pytest.fixture(autouse=True)
def _configure_settings(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://localhost:5173")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


client = TestClient(app)


def test_health_reports_ok_when_supabase_reachable():
    mock_response = MagicMock(status_code=200)
    with patch("app.routers.health.httpx.get", return_value=mock_response) as mock_get:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "supabase_reachable": True}
    mock_get.assert_called_once()


def test_health_reports_degraded_when_supabase_unreachable():
    with patch("app.routers.health.httpx.get", side_effect=Exception("connection refused")):
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "degraded", "supabase_reachable": False}
