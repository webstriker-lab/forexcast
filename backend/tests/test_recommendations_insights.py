import time
from unittest.mock import patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())
client = TestClient(app)


def _auth_headers(sub="test-user-id"):
    token = jwt.encode(
        {"sub": sub, "aud": "authenticated", "exp": int(time.time()) + 3600},
        _PRIVATE_KEY,
        algorithm="ES256",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _configure_settings(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://localhost:5173")
    get_settings.cache_clear()
    monkeypatch.setattr("app.auth._get_signing_key", lambda token: _PRIVATE_KEY.public_key())
    yield
    get_settings.cache_clear()


def test_insights_requires_auth():
    resp = client.get("/recommendations/EUR/USD/insights")
    assert resp.status_code == 401


def test_insights_returns_requires_llm_setup_when_not_configured():
    with patch("app.recommendations.router.is_llm_configured", return_value=False):
        resp = client.get("/recommendations/EUR/USD/insights", headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["requires_llm_setup"] is True
    assert body["sentiment"] is None


def test_insights_returns_sentiment_when_configured():
    articles = [{"title": "Euro strengthens"}, {"title": "b"}, {"title": "c"}]
    with (
        patch("app.recommendations.router.is_llm_configured", return_value=True),
        patch("app.recommendations.router.fetch_articles", return_value=articles),
        patch("app.recommendations.router.score_sentiment", return_value={"score": 0.6, "summary": "Positive outlook"}),
    ):
        resp = client.get("/recommendations/EUR/USD/insights", headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["requires_llm_setup"] is False
    assert body["sentiment"]["score"] == pytest.approx(0.6)
    assert "Positive" in body["sentiment"]["summary"]


def test_insights_returns_null_sentiment_when_articles_empty():
    with (
        patch("app.recommendations.router.is_llm_configured", return_value=True),
        patch("app.recommendations.router.fetch_articles", return_value=[]),
        patch("app.recommendations.router.score_sentiment") as mock_score,
    ):
        resp = client.get("/recommendations/USD/EUR/insights", headers=_auth_headers())
    assert resp.status_code == 200
    mock_score.assert_not_called()
    assert resp.json()["sentiment"] is None