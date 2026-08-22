from unittest.mock import MagicMock, patch

from app.recommendations.supabase_rest import (
    deactivate_alert,
    get_active_alerts,
    get_current_rate,
    get_directed_rate,
    get_latest_predictions,
    get_latest_recommendation,
    get_latest_two_recommendations,
    insert_recommendations,
    record_alert_event,
)


def test_get_latest_predictions_fetches_latest_timestamp_then_matching_rows():
    latest_response = MagicMock()
    latest_response.json.return_value = [{"generated_at": "2026-08-15T18:00:00+00:00"}]
    latest_response.raise_for_status.return_value = None

    rows_response = MagicMock()
    rows_response.json.return_value = [
        {
            "horizon_days": 7,
            "predicted_rate": 90.0,
            "lower_bound": 88.0,
            "upper_bound": 92.0,
            "confidence": "normal",
        },
        {
            "horizon_days": 30,
            "predicted_rate": 95.0,
            "lower_bound": 91.0,
            "upper_bound": 99.0,
            "confidence": "normal",
        },
    ]
    rows_response.raise_for_status.return_value = None

    with patch(
        "app.recommendations.supabase_rest.httpx.get",
        side_effect=[latest_response, rows_response],
    ) as mock_get:
        result = get_latest_predictions("INR")

    assert len(result) == 2
    assert result[0]["horizon_days"] == 7
    assert result[0]["predicted_rate"] == 90.0
    assert mock_get.call_count == 2
    second_call_kwargs = mock_get.call_args_list[1].kwargs
    assert second_call_kwargs["params"]["generated_at"] == "eq.2026-08-15T18:00:00+00:00"


def test_get_latest_predictions_returns_empty_list_when_no_predictions_exist():
    latest_response = MagicMock()
    latest_response.json.return_value = []
    latest_response.raise_for_status.return_value = None

    with patch(
        "app.recommendations.supabase_rest.httpx.get", return_value=latest_response
    ) as mock_get:
        result = get_latest_predictions("INR")

    assert result == []
    mock_get.assert_called_once()


def test_get_current_rate_returns_latest_rate():
    mock_response = MagicMock()
    mock_response.json.return_value = [{"rate": 95.44}]
    mock_response.raise_for_status.return_value = None
    with patch(
        "app.recommendations.supabase_rest.httpx.get", return_value=mock_response
    ) as mock_get:
        result = get_current_rate("INR")

    assert result == 95.44
    args, kwargs = mock_get.call_args
    assert kwargs["params"] == {
        "select": "rate",
        "base_code": "eq.USD",
        "quote_code": "eq.INR",
        "order": "as_of.desc",
        "limit": 1,
    }


def test_get_current_rate_returns_none_when_not_found():
    mock_response = MagicMock()
    mock_response.json.return_value = []
    mock_response.raise_for_status.return_value = None
    with patch("app.recommendations.supabase_rest.httpx.get", return_value=mock_response):
        result = get_current_rate("INR")

    assert result is None


def test_get_directed_rate_returns_one_when_base_equals_quote():
    with patch(
        "app.recommendations.supabase_rest.get_current_rate"
    ) as mock_get_current_rate:
        result = get_directed_rate("INR", "INR")

    assert result == 1.0
    mock_get_current_rate.assert_not_called()


def test_get_directed_rate_delegates_to_get_current_rate_when_base_is_usd():
    with patch(
        "app.recommendations.supabase_rest.get_current_rate", return_value=85.0
    ) as mock_get_current_rate:
        result = get_directed_rate("USD", "INR")

    assert result == 85.0
    mock_get_current_rate.assert_called_once_with("INR")


def test_get_directed_rate_inverts_when_quote_is_usd():
    with patch(
        "app.recommendations.supabase_rest.get_current_rate", return_value=85.0
    ) as mock_get_current_rate:
        result = get_directed_rate("INR", "USD")

    assert result == 1 / 85.0
    mock_get_current_rate.assert_called_once_with("INR")


def test_get_directed_rate_returns_none_when_quote_is_usd_and_base_rate_missing():
    with patch(
        "app.recommendations.supabase_rest.get_current_rate", return_value=None
    ):
        result = get_directed_rate("INR", "USD")

    assert result is None


def test_get_directed_rate_resolves_cross_pair_through_usd_pivot():
    def fake_get_current_rate(quote_code):
        return {"EUR": 0.92, "INR": 85.0}[quote_code]

    with patch(
        "app.recommendations.supabase_rest.get_current_rate",
        side_effect=fake_get_current_rate,
    ):
        result = get_directed_rate("EUR", "INR")

    assert result == 85.0 / 0.92


def test_get_directed_rate_returns_none_when_cross_pair_rate_missing():
    def fake_get_current_rate(quote_code):
        return {"EUR": 0.92, "INR": None}[quote_code]

    with patch(
        "app.recommendations.supabase_rest.get_current_rate",
        side_effect=fake_get_current_rate,
    ):
        result = get_directed_rate("EUR", "INR")

    assert result is None


def test_insert_recommendations_posts_batch():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    rows = [
        {
            "base_code": "USD",
            "quote_code": "INR",
            "recommendation": "wait",
            "reference_horizon_days": 30,
            "current_rate": 95.0,
            "expected_rate": 97.0,
            "lower_bound": 94.0,
            "upper_bound": 100.0,
        }
    ]
    with patch(
        "app.recommendations.supabase_rest.httpx.post", return_value=mock_response
    ) as mock_post:
        insert_recommendations(rows)

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "https://example.supabase.co/rest/v1/recommendations"
    assert kwargs["json"] == rows


def test_get_active_alerts_filters_by_is_active():
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {
            "id": "alert-1",
            "base_code": "USD",
            "quote_code": "INR",
            "alert_type": "threshold",
            "threshold_rate": 85.0,
            "direction": "above",
        }
    ]
    mock_response.raise_for_status.return_value = None
    with patch(
        "app.recommendations.supabase_rest.httpx.get", return_value=mock_response
    ) as mock_get:
        result = get_active_alerts()

    assert len(result) == 1
    assert result[0]["id"] == "alert-1"
    args, kwargs = mock_get.call_args
    assert kwargs["params"]["is_active"] == "eq.true"


def test_get_latest_two_recommendations_returns_values_newest_first():
    mock_response = MagicMock()
    mock_response.json.return_value = [{"recommendation": "act_now"}, {"recommendation": "wait"}]
    mock_response.raise_for_status.return_value = None
    with patch(
        "app.recommendations.supabase_rest.httpx.get", return_value=mock_response
    ) as mock_get:
        result = get_latest_two_recommendations("USD", "INR")

    assert result == ["act_now", "wait"]
    args, kwargs = mock_get.call_args
    assert kwargs["params"]["limit"] == 2


def test_record_alert_event_posts_event():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    with patch(
        "app.recommendations.supabase_rest.httpx.post", return_value=mock_response
    ) as mock_post:
        record_alert_event("alert-1", {"reason": "threshold crossed"})

    args, kwargs = mock_post.call_args
    assert args[0] == "https://example.supabase.co/rest/v1/alert_events"
    assert kwargs["json"] == [{"alert_id": "alert-1", "details": {"reason": "threshold crossed"}}]


def test_deactivate_alert_patches_is_active_false():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    with patch(
        "app.recommendations.supabase_rest.httpx.patch", return_value=mock_response
    ) as mock_patch:
        deactivate_alert("alert-1")

    args, kwargs = mock_patch.call_args
    assert args[0] == "https://example.supabase.co/rest/v1/alerts"
    assert kwargs["params"] == {"id": "eq.alert-1"}
    assert kwargs["json"] == {"is_active": False}


def test_get_latest_recommendation_returns_the_newest_row():
    response = MagicMock()
    response.json.return_value = [
        {
            "recommendation": "act_now",
            "current_rate": 90.5,
            "expected_rate": 92.0,
            "lower_bound": 89.0,
            "upper_bound": 95.0,
            "reference_horizon_days": 30,
            "generated_at": "2026-08-22T10:00:00+00:00",
        }
    ]
    response.raise_for_status.return_value = None

    with patch(
        "app.recommendations.supabase_rest.httpx.get", return_value=response
    ) as mock_get:
        result = get_latest_recommendation("INR")

    assert result["recommendation"] == "act_now"
    assert result["current_rate"] == 90.5
    kwargs = mock_get.call_args.kwargs
    assert kwargs["params"]["quote_code"] == "eq.INR"
    assert kwargs["params"]["base_code"] == "eq.USD"
    assert kwargs["params"]["order"] == "generated_at.desc"
    assert kwargs["params"]["limit"] == 1


def test_get_latest_recommendation_returns_none_when_no_rows_exist():
    response = MagicMock()
    response.json.return_value = []
    response.raise_for_status.return_value = None

    with patch("app.recommendations.supabase_rest.httpx.get", return_value=response):
        result = get_latest_recommendation("INR")

    assert result is None
