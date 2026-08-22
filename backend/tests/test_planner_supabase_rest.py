# backend/tests/test_planner_supabase_rest.py
"""Tests for the planner module's Supabase REST accessors."""
from unittest.mock import MagicMock, patch

from app.planner.supabase_rest import (
    get_user_debts, create_debt, update_debt, delete_debt,
    get_user_income, create_income, update_income, delete_income,
    get_user_savings_goals, create_savings_goal, update_savings_goal, delete_savings_goal,
    get_user_achievements, create_achievement,
    get_user_streaks, upsert_user_streaks,
)


def _mock_response(json_data, status_ok=True):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = json_data
    return response


def test_get_user_debts_filters_active_only_by_default():
    with patch(
        "app.planner.supabase_rest.httpx.get", return_value=_mock_response([{"id": "d1"}])
    ) as mock_get:
        get_user_debts("u1")

    assert mock_get.call_args.kwargs["params"]["is_active"] == "eq.true"


def test_get_user_debts_include_inactive_omits_the_filter():
    with patch(
        "app.planner.supabase_rest.httpx.get", return_value=_mock_response([{"id": "d1"}])
    ) as mock_get:
        get_user_debts("u1", include_inactive=True)

    assert "is_active" not in mock_get.call_args.kwargs["params"]


def test_create_debt_sets_user_id():
    with patch(
        "app.planner.supabase_rest.httpx.post", return_value=_mock_response([{"id": "d1"}])
    ) as mock_post:
        create_debt("u1", {"name": "Loan"})

    assert mock_post.call_args.kwargs["json"]["user_id"] == "u1"


def test_update_debt_allowlists_fields():
    with patch(
        "app.planner.supabase_rest.httpx.patch", return_value=_mock_response([{"id": "d1"}])
    ) as mock_patch:
        update_debt("d1", "u1", {"current_balance": 500, "user_id": "attacker", "currency_code": "EUR"})

    body = mock_patch.call_args.kwargs["json"]
    assert body == {"current_balance": 500}
    params = mock_patch.call_args.kwargs["params"]
    assert params["id"] == "eq.d1"
    assert params["user_id"] == "eq.u1"


def test_delete_debt_returns_true_when_a_row_was_deleted():
    with patch(
        "app.planner.supabase_rest.httpx.patch", return_value=_mock_response([{"id": "d1"}])
    ):
        result = delete_debt("d1", "u1")

    assert result is True


def test_delete_debt_returns_false_when_not_owned_or_missing():
    with patch("app.planner.supabase_rest.httpx.patch", return_value=_mock_response([])):
        result = delete_debt("missing", "u1")

    assert result is False


def test_get_user_income_filters_active_only_by_default():
    with patch(
        "app.planner.supabase_rest.httpx.get", return_value=_mock_response([])
    ) as mock_get:
        get_user_income("u1")

    assert mock_get.call_args.kwargs["params"]["is_active"] == "eq.true"


def test_update_income_allowlists_fields():
    with patch(
        "app.planner.supabase_rest.httpx.patch", return_value=_mock_response([{"id": "i1"}])
    ) as mock_patch:
        update_income("i1", "u1", {"amount": 5000, "currency_code": "EUR"})

    assert mock_patch.call_args.kwargs["json"] == {"amount": 5000}


def test_delete_income_returns_false_when_not_owned_or_missing():
    with patch("app.planner.supabase_rest.httpx.patch", return_value=_mock_response([])):
        result = delete_income("missing", "u1")

    assert result is False


def test_get_user_savings_goals_filters_active_only_by_default():
    with patch(
        "app.planner.supabase_rest.httpx.get", return_value=_mock_response([])
    ) as mock_get:
        get_user_savings_goals("u1")

    assert mock_get.call_args.kwargs["params"]["is_active"] == "eq.true"


def test_update_savings_goal_allowlists_fields():
    with patch(
        "app.planner.supabase_rest.httpx.patch", return_value=_mock_response([{"id": "g1"}])
    ) as mock_patch:
        update_savings_goal("g1", "u1", {"current_saved": 500, "target_currency": "EUR"})

    assert mock_patch.call_args.kwargs["json"] == {"current_saved": 500}


def test_delete_savings_goal_returns_false_when_not_owned_or_missing():
    with patch("app.planner.supabase_rest.httpx.patch", return_value=_mock_response([])):
        result = delete_savings_goal("missing", "u1")

    assert result is False


def test_create_achievement_sets_user_id():
    with patch(
        "app.planner.supabase_rest.httpx.post", return_value=_mock_response([{"id": "a1"}])
    ) as mock_post:
        create_achievement("u1", {"badge_id": "first_goal_set", "metadata": None})

    assert mock_post.call_args.kwargs["json"]["user_id"] == "u1"


def test_get_user_streaks_returns_none_when_no_row():
    with patch("app.planner.supabase_rest.httpx.get", return_value=_mock_response([])):
        result = get_user_streaks("u1")

    assert result is None


def test_upsert_user_streaks_sets_user_id():
    with patch(
        "app.planner.supabase_rest.httpx.post", return_value=_mock_response([{"user_id": "u1"}])
    ) as mock_post:
        upsert_user_streaks("u1", {"daily_checkin_current": 1})

    assert mock_post.call_args.kwargs["json"]["user_id"] == "u1"
