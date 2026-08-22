# backend/tests/test_planner_routes.py
"""Auth tests for the planner routes -- every route must require a
valid bearer token, matching this codebase's convention across every
other router (see test_auth.py for the real-signed-JWT pattern this
follows).
"""
import time
from unittest.mock import patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())


@pytest.fixture(autouse=True)
def _configure_settings(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://localhost:5173")
    get_settings.cache_clear()
    monkeypatch.setattr("app.auth._get_signing_key", lambda token: _PRIVATE_KEY.public_key())
    yield
    get_settings.cache_clear()


client = TestClient(app)


def _auth_headers(sub="test-user-id"):
    token = jwt.encode(
        {"sub": sub, "aud": "authenticated", "exp": int(time.time()) + 3600},
        _PRIVATE_KEY,
        algorithm="ES256",
    )
    return {"Authorization": f"Bearer {token}"}


def test_list_debts_requires_auth():
    response = client.get("/planner/debts")
    assert response.status_code == 401


def test_list_debts_succeeds_with_auth():
    with patch("app.planner.routes.get_user_debts", return_value=[]):
        response = client.get("/planner/debts", headers=_auth_headers())
    assert response.status_code == 200


def test_badges_requires_auth():
    response = client.get("/planner/badges")
    assert response.status_code == 401


def test_badges_succeeds_with_auth():
    response = client.get("/planner/badges", headers=_auth_headers())
    assert response.status_code == 200
    assert "first_debt_paid_off" in response.json()


def test_goals_timeline_returns_error_when_no_contribution_or_date():
    goal = {
        "id": "g1", "name": "Trip", "target_amount": 1000, "current_saved": 0,
        "target_date": None, "monthly_contribution": None, "is_active": True,
    }
    with patch("app.planner.routes.get_user_savings_goals", return_value=[goal]):
        response = client.get("/planner/timeline/goals", headers=_auth_headers())

    assert response.status_code == 200
    assert "error" in response.json()["goals"]["g1"]


def test_goals_timeline_derives_contribution_from_target_date():
    """`derive_monthly_contribution`'s internal date.today() call
    resolves through app.planner.timeline's own `date` import, not
    app.planner.routes' -- routes.py's own `date.fromisoformat(...)` call
    (parsing the goal's stored target_date string into a real date
    object) is left real/unmocked, only timeline.py's `date.today()` is
    patched to a fixed value so this test is deterministic regardless of
    when it's actually run.
    """
    from datetime import date as real_date

    goal = {
        "id": "g1", "name": "Trip", "target_amount": 6000, "current_saved": 0,
        "target_date": "2026-08-01", "monthly_contribution": None, "is_active": True,
    }
    with patch("app.planner.routes.get_user_savings_goals", return_value=[goal]), patch(
        "app.planner.timeline.date"
    ) as mock_date:
        mock_date.today.return_value = real_date(2026, 2, 1)
        response = client.get("/planner/timeline/goals", headers=_auth_headers())

    assert response.status_code == 200
    result = response.json()["goals"]["g1"]
    assert "error" not in result
    # 6 calendar months from 2026-02-01 to 2026-08-01, $6000 remaining -> $1000/month
    assert result["monthly_contribution"] == 1000.0


def test_debts_timeline_converts_via_rates():
    debt = {
        "id": "d1", "name": "Loan", "current_balance": 9200, "interest_rate": 5,
        "minimum_payment": 500, "currency_code": "EUR", "is_active": True,
    }
    with patch("app.planner.routes.get_user_debts", return_value=[debt]), patch(
        "app.planner.routes.get_current_rate", return_value=0.92
    ):
        response = client.get("/planner/timeline/debts", headers=_auth_headers())

    assert response.status_code == 200
    assert response.json()["summary"]["total_balance"] == 10000.0


def test_check_achievements_sees_inactive_debts():
    with patch("app.planner.routes.get_user_debts") as mock_get_debts, patch(
        "app.planner.routes.get_user_savings_goals", return_value=[]
    ), patch("app.planner.routes.get_user_achievements", return_value=[]), patch(
        "app.planner.routes.get_user_streaks", return_value=None
    ), patch("app.planner.routes.create_achievement", return_value={}):
        mock_get_debts.return_value = []
        client.post("/planner/achievements/check", headers=_auth_headers())

    assert mock_get_debts.call_args.kwargs.get("include_inactive") is True
