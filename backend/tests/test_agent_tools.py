from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.agent.tools import ToolArgumentError, call_tool


def _http_status_error(status_code):
    request = httpx.Request("PATCH", "https://example.supabase.co/rest/v1/alerts")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError("bad request", request=request, response=response)


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


# -- Fix 3: 4xx from a Supabase write becomes a clean tool error --------


def test_create_alert_returns_error_shape_on_4xx_from_supabase():
    with patch(
        "app.agent.tools.create_alert_for_user",
        side_effect=_http_status_error(400),
    ):
        result = call_tool(
            "create_alert",
            {"quote_code": "EURO", "alert_type": "threshold", "threshold_rate": 1.1, "direction": "down"},
            "u1",
        )

    assert "error" in result


def test_update_alert_returns_error_shape_on_4xx_from_supabase():
    with patch(
        "app.agent.tools.update_alert_for_user",
        side_effect=_http_status_error(409),
    ):
        result = call_tool("update_alert", {"alert_id": "not-a-uuid", "is_active": False}, "u1")

    assert "error" in result


def test_delete_alert_returns_error_shape_on_4xx_from_supabase():
    with patch(
        "app.agent.tools.delete_alert_for_user",
        side_effect=_http_status_error(400),
    ):
        result = call_tool("delete_alert", {"alert_id": "not-a-uuid"}, "u1")

    assert "error" in result


def test_create_alert_reraises_on_5xx_from_supabase():
    with patch(
        "app.agent.tools.create_alert_for_user",
        side_effect=_http_status_error(500),
    ):
        with pytest.raises(httpx.HTTPStatusError):
            call_tool(
                "create_alert",
                {"quote_code": "EUR", "alert_type": "threshold", "threshold_rate": 1.1, "direction": "below"},
                "u1",
            )


def test_update_alert_returns_error_shape_when_no_fields_to_update():
    with patch("app.agent.tools.update_alert_for_user") as mock_update:
        result = call_tool("update_alert", {"alert_id": "a1"}, "u1")

    mock_update.assert_not_called()
    assert "error" in result


# -- Fix 4: explicit null argument values are treated as missing --------


def test_get_forecast_treats_explicit_null_arguments_as_missing():
    with pytest.raises(ToolArgumentError):
        call_tool("get_forecast", {"quote_code": None, "horizon_days": 30}, "u1")


# -- Fix 5: horizon_days is type-coerced before comparison --------------


def test_get_forecast_coerces_string_horizon_days_and_matches():
    predictions = [
        {"horizon_days": 30, "predicted_rate": 92.0, "lower_bound": 89.0, "upper_bound": 95.0, "confidence": "low"},
    ]
    with patch("app.agent.tools.get_latest_predictions", return_value=predictions):
        result = call_tool("get_forecast", {"quote_code": "INR", "horizon_days": "30"}, "u1")

    assert result["predicted_rate"] == 92.0


def test_get_forecast_raises_on_non_numeric_horizon_days():
    with pytest.raises(ToolArgumentError):
        call_tool("get_forecast", {"quote_code": "INR", "horizon_days": "not-a-number"}, "u1")


# -- Fix 9: update_alert/delete_alert scope by the authenticated user_id --


def test_update_alert_uses_user_id_from_argument_not_from_model_arguments():
    with patch("app.agent.tools.update_alert_for_user", return_value={"id": "a1"}) as mock_update:
        call_tool(
            "update_alert",
            {"alert_id": "a1", "is_active": False, "user_id": "attacker-supplied"},
            "real-user-id",
        )

    assert mock_update.call_args.args[0] == "real-user-id"


def test_delete_alert_uses_user_id_from_argument_not_from_model_arguments():
    with patch("app.agent.tools.delete_alert_for_user", return_value=True) as mock_delete:
        call_tool(
            "delete_alert",
            {"alert_id": "a1", "user_id": "attacker-supplied"},
            "real-user-id",
        )

    assert mock_delete.call_args.args[0] == "real-user-id"
