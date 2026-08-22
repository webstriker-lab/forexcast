from unittest.mock import patch

import pytest

from app.agent.tools import ToolArgumentError, call_tool


def test_get_forecast_returns_matching_horizon():
    predictions = [
        {"horizon_days": 7, "predicted_rate": 90.0, "lower_bound": 88.0, "upper_bound": 92.0, "confidence": "normal"},
        {"horizon_days": 30, "predicted_rate": 92.0, "lower_bound": 89.0, "upper_bound": 95.0, "confidence": "low"},
    ]
    with patch("app.agent.tools.get_latest_predictions", return_value=predictions):
        result = call_tool("get_forecast", {"quote_code": "INR", "horizon_days": 30}, "u1")

    assert result["predicted_rate"] == 92.0
    assert result["confidence"] == "low"


def test_get_forecast_returns_error_shape_when_horizon_not_found():
    with patch("app.agent.tools.get_latest_predictions", return_value=[]):
        result = call_tool("get_forecast", {"quote_code": "INR", "horizon_days": 30}, "u1")

    assert "error" in result


def test_get_forecast_requires_quote_code_and_horizon_days():
    with pytest.raises(ToolArgumentError):
        call_tool("get_forecast", {"quote_code": "INR"}, "u1")


def test_get_news_summary_returns_error_shape_when_none_scored_today():
    with patch("app.agent.tools.get_latest_news_sentiment", return_value=None):
        result = call_tool("get_news_summary", {"quote_code": "INR"}, "u1")

    assert "error" in result


def test_get_recommendation_passes_through_result():
    with patch(
        "app.agent.tools.get_latest_recommendation",
        return_value={"recommendation": "wait"},
    ):
        result = call_tool("get_recommendation", {"quote_code": "INR"}, "u1")

    assert result == {"recommendation": "wait"}


def test_create_alert_uses_user_id_from_argument_not_from_model_arguments():
    with patch("app.agent.tools.create_alert_for_user") as mock_create:
        mock_create.return_value = {"id": "a1"}
        call_tool(
            "create_alert",
            {"quote_code": "EUR", "alert_type": "threshold", "threshold_rate": 1.1, "direction": "below", "user_id": "attacker-supplied"},
            "real-user-id",
        )

    assert mock_create.call_args.args[0] == "real-user-id"


def test_list_alerts_scopes_by_user_id():
    with patch("app.agent.tools.list_alerts_for_user", return_value=[{"id": "a1"}]) as mock_list:
        result = call_tool("list_alerts", {}, "u1")

    mock_list.assert_called_once_with("u1")
    assert result == {"alerts": [{"id": "a1"}]}


def test_update_alert_returns_error_shape_when_not_owned():
    with patch("app.agent.tools.update_alert_for_user", return_value=None):
        result = call_tool("update_alert", {"alert_id": "not-mine", "is_active": False}, "u1")

    assert "error" in result


def test_delete_alert_returns_error_shape_when_not_owned():
    with patch("app.agent.tools.delete_alert_for_user", return_value=False):
        result = call_tool("delete_alert", {"alert_id": "not-mine"}, "u1")

    assert "error" in result


def test_call_tool_raises_for_unknown_tool_name():
    with pytest.raises(ValueError):
        call_tool("not_a_real_tool", {}, "u1")
