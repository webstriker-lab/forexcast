from unittest.mock import MagicMock, patch

from app.prediction.supabase_rest import (
    get_backtest_stats,
    get_rate_series,
    insert_predictions,
    upsert_backtest_stats,
)


def test_get_rate_series_returns_parallel_date_and_rate_lists():
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"as_of": "2020-01-01", "rate": 0.9},
        {"as_of": "2020-01-02", "rate": 0.91},
    ]
    mock_response.raise_for_status.return_value = None
    with patch(
        "app.prediction.supabase_rest.httpx.get", return_value=mock_response
    ) as mock_get:
        dates, rates = get_rate_series("EUR")

    assert dates == ["2020-01-01", "2020-01-02"]
    assert rates == [0.9, 0.91]
    args, kwargs = mock_get.call_args
    assert args[0] == "https://example.supabase.co/rest/v1/rates_cache"
    assert kwargs["params"] == {
        "select": "as_of,rate",
        "base_code": "eq.USD",
        "quote_code": "eq.EUR",
        "order": "as_of.asc",
        "limit": 1000,
        "offset": 0,
    }


def test_get_rate_series_paginates_across_multiple_pages():
    # First page is exactly PAGE_SIZE rows, forcing a second request; second
    # page is a partial page, which should terminate the loop.
    page_size = 1000
    first_page_rows = [
        {"as_of": f"2020-01-{i:04d}", "rate": 1.0 + i} for i in range(page_size)
    ]
    second_page_rows = [
        {"as_of": "2020-02-01", "rate": 2000.0},
        {"as_of": "2020-02-02", "rate": 2001.0},
    ]
    first_response = MagicMock()
    first_response.json.return_value = first_page_rows
    first_response.raise_for_status.return_value = None
    second_response = MagicMock()
    second_response.json.return_value = second_page_rows
    second_response.raise_for_status.return_value = None

    with patch(
        "app.prediction.supabase_rest.httpx.get",
        side_effect=[first_response, second_response],
    ) as mock_get:
        dates, rates = get_rate_series("EUR")

    assert mock_get.call_count == 2
    assert len(dates) == page_size + 2
    assert len(rates) == page_size + 2
    assert dates[-2:] == ["2020-02-01", "2020-02-02"]
    assert rates[-2:] == [2000.0, 2001.0]

    second_call_kwargs = mock_get.call_args_list[1].kwargs
    assert second_call_kwargs["params"]["offset"] == page_size


def test_insert_predictions_posts_batch():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    rows = [
        {
            "base_code": "USD",
            "quote_code": "EUR",
            "horizon_days": 7,
            "predicted_rate": 0.87,
            "lower_bound": 0.85,
            "upper_bound": 0.89,
            "confidence": "normal",
        }
    ]
    with patch(
        "app.prediction.supabase_rest.httpx.post", return_value=mock_response
    ) as mock_post:
        insert_predictions(rows)

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "https://example.supabase.co/rest/v1/predictions"
    assert kwargs["json"] == rows


def test_get_backtest_stats_returns_stats_when_found():
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"error_lower_pct": -0.02, "error_upper_pct": 0.03, "volatility_p90": 0.015}
    ]
    mock_response.raise_for_status.return_value = None
    with patch(
        "app.prediction.supabase_rest.httpx.get", return_value=mock_response
    ) as mock_get:
        result = get_backtest_stats("EUR", 30)

    assert result == {
        "error_lower_pct": -0.02,
        "error_upper_pct": 0.03,
        "volatility_p90": 0.015,
    }
    args, kwargs = mock_get.call_args
    assert kwargs["params"] == {
        "select": "error_lower_pct,error_upper_pct,volatility_p90",
        "quote_code": "eq.EUR",
        "horizon_days": "eq.30",
    }


def test_get_backtest_stats_returns_none_when_not_found():
    mock_response = MagicMock()
    mock_response.json.return_value = []
    mock_response.raise_for_status.return_value = None
    with patch("app.prediction.supabase_rest.httpx.get", return_value=mock_response):
        result = get_backtest_stats("EUR", 30)

    assert result is None


def test_upsert_backtest_stats_posts_with_merge_duplicates():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    rows = [
        {
            "quote_code": "EUR",
            "horizon_days": 30,
            "error_lower_pct": -0.02,
            "error_upper_pct": 0.03,
            "volatility_p90": 0.015,
            "sample_count": 240,
        }
    ]
    with patch(
        "app.prediction.supabase_rest.httpx.post", return_value=mock_response
    ) as mock_post:
        upsert_backtest_stats(rows)

    args, kwargs = mock_post.call_args
    assert args[0] == "https://example.supabase.co/rest/v1/backtest_stats"
    assert kwargs["params"] == {"on_conflict": "quote_code,horizon_days"}
    assert kwargs["headers"]["Prefer"] == "resolution=merge-duplicates"
    assert kwargs["json"] == rows
