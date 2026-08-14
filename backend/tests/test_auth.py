import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from app.main import app
from app.config import get_settings

_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())
_OTHER_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())


@pytest.fixture(autouse=True)
def _configure_settings(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://localhost:5173")
    get_settings.cache_clear()
    # Supabase's real JWKS endpoint isn't reachable in tests; return the
    # matching public key directly instead of fetching it over HTTP.
    monkeypatch.setattr(
        "app.auth._get_signing_key",
        lambda token: _PRIVATE_KEY.public_key(),
    )
    yield
    get_settings.cache_clear()


client = TestClient(app)


def _make_token(sub="user-123", exp_delta=3600, aud="authenticated", key=_PRIVATE_KEY):
    payload = {"sub": sub, "aud": aud, "exp": int(time.time()) + exp_delta}
    return jwt.encode(payload, key, algorithm="ES256")


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


def test_me_with_wrong_key_returns_401():
    token = _make_token(key=_OTHER_PRIVATE_KEY)
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
