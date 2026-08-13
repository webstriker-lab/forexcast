import time

import jwt
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import get_settings

TEST_SECRET = "test-jwt-secret-please-do-not-use-in-prod"


@pytest.fixture(autouse=True)
def _configure_settings(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", TEST_SECRET)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


client = TestClient(app)


def _make_token(sub="user-123", exp_delta=3600, aud="authenticated"):
    payload = {"sub": sub, "aud": aud, "exp": int(time.time()) + exp_delta}
    return jwt.encode(payload, TEST_SECRET, algorithm="HS256")


def test_me_with_valid_token_returns_user_id():
    token = _make_token()
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {"user_id": "user-123"}


def test_me_without_token_returns_401():
    response = client.get("/me")
    assert response.status_code == 401


def test_me_with_expired_token_returns_401():
    token = _make_token(exp_delta=-3600)
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_me_with_wrong_secret_returns_401():
    token = jwt.encode(
        {"sub": "user-123", "aud": "authenticated", "exp": int(time.time()) + 3600},
        "wrong-secret",
        algorithm="HS256",
    )
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
