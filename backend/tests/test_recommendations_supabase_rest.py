from unittest.mock import MagicMock, patch

from app.recommendations.supabase_rest import (
    get_current_rate,
    get_latest_predictions,
    insert_recommendations,
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
